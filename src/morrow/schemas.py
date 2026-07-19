"""The WorkflowSpec: an evidence-backed, abstract description of a demonstrated task.

This is the one artifact MK2 produces. Everything else in the package exists to fill
it in or to check it. The design turns on a distinction demonstration-learning code
usually collapses — the difference between what the worker *did* (`OrderRelation.observed`),
what the task *requires* (`OrderRelation.necessity`), and what we simply do not know
(`Unknown`, and `necessity="unknown"`).

These types are the public contract. They carry no behaviour — validation lives in
`validate.py` so the schema stays a pure description of shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Source = Literal["video", "transcript", "description"]


class Evidence(BaseModel):
    """A pointer to where a claim came from. Every inferred fact must cite at least one.

    For a `video` source, `start_s`/`end_s` locate the moment relied on. For
    `transcript`/`description`, `quote` holds the exact words. `note` is a one-line
    justification.
    """

    source: Source
    start_s: float | None = None
    end_s: float | None = None
    quote: str | None = None
    note: str | None = None


class Entity(BaseModel):
    """A thing that participates in the task — an object, tool, container, or agent.

    `role` is the semantic role in the task (e.g. "container", "item", "tool"), kept
    as free text: the vocabulary is not stable enough yet to freeze into an enum.
    """

    id: str
    name: str
    role: str
    evidence: list[Evidence]


class StateFact(BaseModel):
    """A condition that holds at a point in time. Used for both initial state and goals."""

    description: str
    entity_ids: list[str]
    evidence: list[Evidence]


class Step(BaseModel):
    """A single demonstrated action, with its temporal span in the video (seconds)."""

    id: str
    action: str  # the verb: "pick", "place", "insert", "close"
    description: str
    entity_ids: list[str]
    start_s: float | None = None
    end_s: float | None = None
    evidence: list[Evidence]
    confidence: float


class OrderRelation(BaseModel):
    """An ordering between two steps, keeping observed and required strictly apart.

    `observed` records what the demonstration showed. `necessity` records whether the
    order *must* hold — a separate question the model must not conflate with having
    merely seen it. It defaults to "unknown": order is soft unless narration, the
    description, or physical mechanics make it mandatory.
    """

    before: str  # Step.id
    after: str  # Step.id
    observed: bool
    necessity: Literal["required", "not_required", "unknown"] = "unknown"
    rationale: str
    evidence: list[Evidence]


class Constraint(BaseModel):
    """A hard rule the task imposes — must always hold."""

    description: str
    evidence: list[Evidence]
    confidence: float


class Preference(BaseModel):
    """A soft preference — worth following, not mandatory."""

    description: str
    evidence: list[Evidence]
    confidence: float


class RepeatSpec(BaseModel):
    """How and when the task repeats, if it does."""

    description: str
    termination_condition: str
    evidence: list[Evidence]


class Unknown(BaseModel):
    """Something the model could not determine, phrased as a question worth asking."""

    question: str
    why_it_matters: str


class WorkflowSpec(BaseModel):
    """The abstract, evidence-backed task specification inferred from one demonstration."""

    task_summary: str
    entities: list[Entity]
    initial_state: list[StateFact]
    steps: list[Step]
    final_goals: list[StateFact]
    ordering: list[OrderRelation]
    hard_constraints: list[Constraint]
    soft_preferences: list[Preference]
    repeat: RepeatSpec | None = None
    unknowns: list[Unknown]
    confidence: float
    status: Literal["accepted", "needs_confirmation", "needs_new_video"]
