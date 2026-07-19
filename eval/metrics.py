"""Scoring a predicted WorkflowSpec against a gold one.

Deliberately honest about what a machine can and cannot check here. Referential and
count-level facts are computed deterministically. The two numbers that actually gate
the thesis — goal accuracy and *invented* hard constraints — need human or model
judgement to compare semantically, so this reports the raw material for that judgement
rather than faking it with string equality.
"""

from __future__ import annotations

from morrow.schemas import WorkflowSpec


def score(pred: WorkflowSpec, gold: WorkflowSpec) -> dict:
    return {
        "pred_steps": len(pred.steps),
        "gold_steps": len(gold.steps),
        "pred_hard_constraints": len(pred.hard_constraints),
        "gold_hard_constraints": len(gold.hard_constraints),
        # A key MK2 failure mode: asserting a hard constraint the task does not have.
        # Positive means the model over-constrained; grade the surplus by hand.
        "surplus_hard_constraints": max(0, len(pred.hard_constraints) - len(gold.hard_constraints)),
        "pred_goals": len(pred.final_goals),
        "gold_goals": len(gold.final_goals),
        "pred_required_orderings": sum(1 for r in pred.ordering if r.necessity == "required"),
        "gold_required_orderings": sum(1 for r in gold.ordering if r.necessity == "required"),
        "pred_status": pred.status,
        # Left for the grader: does each gold goal appear in pred, and is every
        # pred hard_constraint actually load-bearing? These are semantic, not string.
        "needs_human_grade": ["goal_recall", "hard_constraint_precision"],
    }
