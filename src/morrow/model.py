"""The model passes: frames + words -> grounded observations -> WorkflowSpec.

Two explicit calls, not one. The observation pass reports only what is visible or
stated. The synthesis pass turns those observations into a WorkflowSpec and is the
only place the observed / required / unknown distinction gets decided. Splitting them
keeps grounding honest: the synthesizer can only build on facts the observer already
tied to a timestamp or a quote.

One model, called directly. No adapter interface yet — there is exactly one backend,
and an abstraction for a second one that does not exist would be dead weight.
"""

from __future__ import annotations

import base64

import anthropic
from pydantic import BaseModel

from .ingest import Frame, VideoMeta
from .schemas import WorkflowSpec

MODEL = "claude-opus-4-8"


class ObservedEntity(BaseModel):
    name: str
    description: str
    role_guess: str
    first_seen_s: float | None = None


class ObservedEvent(BaseModel):
    description: str
    kind: str  # "action" (something changes) or "state" (a static condition)
    start_s: float | None = None
    end_s: float | None = None
    entities: list[str]


class NarrationClaim(BaseModel):
    text: str
    source: str  # "transcript" or "description"
    implies: str


class Observations(BaseModel):
    entities: list[ObservedEntity]
    events: list[ObservedEvent]
    narration_claims: list[NarrationClaim]
    notes: str


OBSERVE_SYSTEM = """\
You observe a single task demonstration from sampled video frames and a written \
description. Report only what is visible in a frame or stated in the words — never \
invent an entity, action, or state the evidence does not support. For every event, \
give the video timestamps (seconds) you relied on. Separate actions (something \
changes) from static state. Keep entity names concrete and consistent across events. \
When something is ambiguous, say so in `notes` rather than guessing. Do not infer the \
purpose or the required ordering of the task — that is a later step."""

SYNTHESIZE_SYSTEM = """\
You convert grounded observations of one task demonstration into a WorkflowSpec: an \
abstract, evidence-backed description of the task a robot should later perform.

Rules:
- Every entity, step, state, goal, constraint, and preference must cite at least one \
piece of evidence — a video timespan, or a quote from the transcript or description. \
Never introduce anything the observations or description do not support.
- Keep demonstrated and required strictly apart. For each ordering relation set \
`observed` to whether the demo showed that order, and set `necessity` independently: \
"required" only when narration, the description, or physical mechanics make the order \
mandatory (e.g. a container must be open before it can be filled); "not_required" when \
the order was clearly incidental; "unknown" otherwise. Default to "unknown" — never \
upgrade an observed order to required without a stated reason.
- Mark `hard_constraints` only for rules that must always hold. When in doubt it is a \
`soft_preference` or an `unknown`, not a hard constraint.
- Put genuine gaps in `unknowns` as concrete, answerable questions.
- Set `status`: "accepted" if the spec is confident and complete enough to act on; \
"needs_confirmation" if one targeted question would resolve the ambiguity; \
"needs_new_video" if the demonstration is too incomplete to specify the task.
- Report calibrated `confidence` in [0, 1]. Do not manufacture detail to seem complete."""


def observe(
    frames: list[Frame],
    meta: VideoMeta,
    description: str,
    transcript: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> Observations:
    """First pass: extract grounded entities, events, and narration claims from the demo."""
    client = client or anthropic.Anthropic()

    blocks: list[dict] = [{"type": "text", "text": _observe_intro(meta, description, transcript)}]
    for f in frames:
        blocks.append({"type": "text", "text": f"Frame at t={f.timestamp_s:.2f}s:"})
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(f.jpeg).decode("ascii"),
            },
        })

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=OBSERVE_SYSTEM,
        messages=[{"role": "user", "content": blocks}],
        output_format=Observations,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"observation pass returned no parseable result (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def synthesize(
    observations: Observations,
    description: str,
    transcript: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> WorkflowSpec:
    """Second pass: turn grounded observations into a validated WorkflowSpec."""
    client = client or anthropic.Anthropic()

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYNTHESIZE_SYSTEM,
        messages=[{"role": "user", "content": _synthesis_input(observations, description, transcript)}],
        output_format=WorkflowSpec,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"synthesis pass returned no parseable result (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def _observe_intro(meta: VideoMeta, description: str, transcript: str | None) -> str:
    lines = [
        f"Video is {meta.duration_s:.1f}s long. Frames below are labelled with their timestamps.",
        f"\nUser's written description of the task:\n{description}",
    ]
    if transcript:
        lines.append(f"\nTranscript of in-video narration:\n{transcript}")
    return "\n".join(lines)


def _synthesis_input(observations: Observations, description: str, transcript: str | None) -> str:
    lines = [
        f"User's written description of the task:\n{description}",
    ]
    if transcript:
        lines.append(f"\nTranscript of in-video narration:\n{transcript}")
    lines.append(f"\nGrounded observations (JSON):\n{observations.model_dump_json(indent=2)}")
    return "\n".join(lines)
