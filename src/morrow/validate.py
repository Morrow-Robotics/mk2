"""Deterministic checks on a WorkflowSpec. No model calls — just invariants.

These enforce the MK2 rules a language model cannot be trusted to keep on its own:
every inferred fact cites evidence, every entity and step referenced actually exists,
and every video timestamp falls within the clip. `validate` returns a list of issues;
an empty list means the spec is internally coherent — not that it is correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .ingest import VideoMeta
from .schemas import Evidence, WorkflowSpec

# ffmpeg input-seek lands a hair past the requested time; allow a small overshoot
# past the reported duration before calling a timestamp out of range.
_DURATION_SLACK_S = 1.0


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning"]
    message: str


def validate(spec: WorkflowSpec, meta: VideoMeta) -> list[Issue]:
    issues: list[Issue] = []
    entity_ids = {e.id for e in spec.entities}
    step_ids = {s.id for s in spec.steps}

    _check_references(spec, entity_ids, step_ids, issues)
    _check_evidence_present(spec, issues)
    _check_necessity_grounded(spec, issues)
    _check_evidence_bounds(spec, meta, issues)
    return issues


def _check_necessity_grounded(spec, issues) -> None:
    # Critical invariant: an order may only be called required/not_required with
    # evidence. "Observed" alone never establishes necessity — that stays unknown.
    for rel in spec.ordering:
        if rel.necessity != "unknown" and not rel.evidence:
            issues.append(Issue(
                "error",
                f"ordering {rel.before!r}->{rel.after!r} claims necessity "
                f"{rel.necessity!r} with no evidence",
            ))


def _check_references(spec, entity_ids, step_ids, issues) -> None:
    for rel in spec.ordering:
        for ref in (rel.before, rel.after):
            if ref not in step_ids:
                issues.append(Issue("error", f"ordering references unknown step id {ref!r}"))
    for step in spec.steps:
        for ref in step.entity_ids:
            if ref not in entity_ids:
                issues.append(Issue("error", f"step {step.id!r} references unknown entity id {ref!r}"))
    for fact in spec.initial_state + spec.final_goals:
        for ref in fact.entity_ids:
            if ref not in entity_ids:
                issues.append(Issue("error", f"state fact references unknown entity id {ref!r}"))


def _check_evidence_present(spec, issues) -> None:
    # A fact with no evidence is exactly the failure mode MK2 exists to prevent.
    for e in spec.entities:
        if not e.evidence:
            issues.append(Issue("error", f"entity {e.id!r} has no evidence"))
    for s in spec.steps:
        if not s.evidence:
            issues.append(Issue("error", f"step {s.id!r} has no evidence"))
    for c in spec.hard_constraints:
        if not c.evidence:
            issues.append(Issue("error", f"hard constraint {c.description!r} has no evidence"))
    for g in spec.final_goals:
        if not g.evidence:
            issues.append(Issue("error", f"goal {g.description!r} has no evidence"))


def _check_evidence_bounds(spec, meta, issues) -> None:
    limit = meta.duration_s + _DURATION_SLACK_S
    for ev in _all_evidence(spec):
        if ev.source != "video":
            continue
        for t in (ev.start_s, ev.end_s):
            if t is not None and (t < 0 or t > limit):
                issues.append(Issue("error", f"video evidence timestamp {t:.2f}s is outside [0, {meta.duration_s:.2f}s]"))


def _all_evidence(spec: WorkflowSpec) -> list[Evidence]:
    out: list[Evidence] = []
    for e in spec.entities:
        out += e.evidence
    for s in spec.steps:
        out += s.evidence
    for f in spec.initial_state + spec.final_goals:
        out += f.evidence
    for rel in spec.ordering:
        out += rel.evidence
    for c in spec.hard_constraints:
        out += c.evidence
    for p in spec.soft_preferences:
        out += p.evidence
    if spec.repeat:
        out += spec.repeat.evidence
    return out
