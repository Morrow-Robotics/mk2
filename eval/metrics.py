"""The Baseline-0 scoreboard. Reports many small numbers, never one blended score.

Three groups:
  self_metrics    — computable from a spec alone (evidence coverage, grounding, status)
  gold_metrics    — needs a hand-authored gold spec (entity P/R, action F1, goals, order)
  critical_checks — the pass/fail gates Baseline-0 is really testing

Alignment across specs is by normalized name/action, not by id (ids never match across
pred and gold). That makes entity and step matching strict and approximate — a missed
match undercounts rather than overcounts. Numbers needing human judgement are flagged,
not faked with string equality.
"""

from __future__ import annotations

import re
from collections import Counter

from morrow.schemas import WorkflowSpec

# Bump when any metric definition changes. Scores are keyed by this, so an old score
# and a new one never silently blur together.
METRICS_VERSION = "m0"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower()).strip(" .,;:!?")


def _prf(pred: Counter, gold: Counter) -> dict:
    overlap = sum((pred & gold).values())
    p = overlap / sum(pred.values()) if pred else 0.0
    r = overlap / sum(gold.values()) if gold else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def _facts_with_evidence(spec: WorkflowSpec) -> tuple[int, int]:
    """(#facts carrying >=1 evidence, #facts total). Every inferred thing is a fact."""
    groups = [spec.entities, spec.steps, spec.initial_state, spec.final_goals,
              spec.ordering, spec.hard_constraints, spec.soft_preferences]
    facts = [f for g in groups for f in g]
    if spec.repeat:
        facts.append(spec.repeat)
    covered = sum(1 for f in facts if getattr(f, "evidence", None))
    return covered, len(facts)


def self_metrics(spec: WorkflowSpec, has_error_issues: bool) -> dict:
    covered, total = _facts_with_evidence(spec)
    return {
        "status": spec.status,
        "confidence": spec.confidence,
        "num_entities": len(spec.entities),
        "num_steps": len(spec.steps),
        "num_goals": len(spec.final_goals),
        "num_hard_constraints": len(spec.hard_constraints),
        "num_unknowns": len(spec.unknowns),
        "orderings": {
            "observed": sum(1 for r in spec.ordering if r.observed),
            "required": sum(1 for r in spec.ordering if r.necessity == "required"),
            "not_required": sum(1 for r in spec.ordering if r.necessity == "not_required"),
            "unknown": sum(1 for r in spec.ordering if r.necessity == "unknown"),
        },
        "evidence_coverage": round(covered / total, 3) if total else 1.0,
        "facts_missing_evidence": total - covered,
        "validation_pass": not has_error_issues,
    }


def gold_metrics(pred: WorkflowSpec, gold: WorkflowSpec) -> dict:
    ents = _prf(Counter(_norm(e.name) for e in pred.entities),
                Counter(_norm(e.name) for e in gold.entities))
    acts = _prf(Counter(_norm(s.action) for s in pred.steps),
                Counter(_norm(s.action) for s in gold.steps))

    pred_goals = {_norm(g.description) for g in pred.final_goals}
    gold_goals = {_norm(g.description) for g in gold.final_goals}
    goal_recall = len(pred_goals & gold_goals) / len(gold_goals) if gold_goals else 1.0

    order = _order_necessity_agreement(pred, gold)
    invented_entities = sorted(
        {_norm(e.name) for e in pred.entities} - {_norm(e.name) for e in gold.entities}
    )

    return {
        "entity": ents,
        "action_f1": acts,
        "final_goal_exact_set_match": pred_goals == gold_goals,
        "final_goal_recall": round(goal_recall, 3),
        "order_necessity": order,
        "hard_constraints": {
            "pred": len(pred.hard_constraints),
            "gold": len(gold.hard_constraints),
            "surplus": max(0, len(pred.hard_constraints) - len(gold.hard_constraints)),
        },
        "invented_entities": invented_entities,
        # Semantic calls a string comparison can't make honestly:
        "needs_human_grade": ["hard_constraint_precision", "goal_semantic_match"],
    }


def _order_necessity_agreement(pred: WorkflowSpec, gold: WorkflowSpec) -> dict:
    """Agreement on necessity for step-pairs present in both, keyed by action verbs.

    Step ids differ across specs, so pairs are identified by (before_action, after_action).
    Approximate when a spec repeats an action; reported as such via the sample size.
    """
    pm = _necessity_by_action_pair(pred)
    gm = _necessity_by_action_pair(gold)
    common = pm.keys() & gm.keys()
    agree = sum(1 for k in common if pm[k] == gm[k])
    return {
        "common_pairs": len(common),
        "agreement": round(agree / len(common), 3) if common else None,
    }


def _necessity_by_action_pair(spec: WorkflowSpec) -> dict[tuple[str, str], str]:
    action = {s.id: _norm(s.action) for s in spec.steps}
    out: dict[tuple[str, str], str] = {}
    for r in spec.ordering:
        if r.before in action and r.after in action:
            out[(action[r.before], action[r.after])] = r.necessity
    return out


def critical_checks(spec: WorkflowSpec, self_m: dict, role: str, gold_m: dict | None) -> dict:
    """The Baseline-0 gates. None means 'cannot decide without gold'."""
    ungrounded_necessity = any(r.necessity != "unknown" and not r.evidence for r in spec.ordering)
    return {
        # Every entity and step traces to observation evidence.
        "all_facts_traceable": self_m["facts_missing_evidence"] == 0,
        # Observed order stays unknown unless evidence establishes necessity.
        "necessity_grounded": not ungrounded_necessity,
        # The negative video must not yield an accepted workflow.
        "negative_not_accepted": role != "negative" or spec.status != "accepted",
        # Zero invented hard constraints — needs gold to judge invention.
        "zero_invented_hard_constraints": (gold_m["hard_constraints"]["surplus"] == 0
                                           if gold_m else None),
    }
