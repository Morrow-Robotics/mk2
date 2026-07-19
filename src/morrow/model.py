"""The model passes: frames + words -> grounded observations -> WorkflowSpec.

Two explicit calls, not one. The observation pass reports only what is visible or
stated. The synthesis pass turns those observations into a WorkflowSpec and is the
only place the observed / required / unknown distinction gets decided. Splitting them
keeps grounding honest: the synthesizer can only build on facts the observer already
tied to a timestamp or a quote.

One model, called directly. No adapter interface yet — there is exactly one backend,
and an abstraction for a second one that does not exist would be dead weight.

The two system prompts below are frozen as prompt version v0 (see PROMPT_VERSION).
`prompt_fingerprint()` hashes them so a run log can prove which prompt produced it.
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel

from .ingest import Frame, VideoMeta
from .schemas import WorkflowSpec

MODEL = "claude-opus-4-8"
PROMPT_VERSION = "v0"


@dataclass
class PassResult:
    """One model pass: the parsed object plus everything a run log needs to keep."""

    parsed: object  # Observations | WorkflowSpec
    raw_json: str
    usage: dict
    latency_s: float


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


def prompt_fingerprint() -> dict:
    """Model id, prompt version, and content hashes — the proof of what a run used."""
    return {
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "observe_system_sha256": hashlib.sha256(OBSERVE_SYSTEM.encode()).hexdigest(),
        "synthesize_system_sha256": hashlib.sha256(SYNTHESIZE_SYSTEM.encode()).hexdigest(),
    }


def observe(
    frames: list[Frame],
    meta: VideoMeta,
    description: str,
    transcript: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> PassResult:
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

    t0 = time.perf_counter()
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=OBSERVE_SYSTEM,
        messages=[{"role": "user", "content": blocks}],
        output_format=Observations,
    )
    latency = time.perf_counter() - t0
    if resp.parsed_output is None:
        raise RuntimeError(f"observation pass returned no parseable result (stop_reason={resp.stop_reason})")
    return PassResult(resp.parsed_output, _raw_text(resp), _usage(resp), latency)


def synthesize(
    observations: Observations,
    description: str,
    transcript: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> PassResult:
    """Second pass: turn grounded observations into a WorkflowSpec."""
    client = client or anthropic.Anthropic()

    t0 = time.perf_counter()
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYNTHESIZE_SYSTEM,
        messages=[{"role": "user", "content": _synthesis_input(observations, description, transcript)}],
        output_format=WorkflowSpec,
    )
    latency = time.perf_counter() - t0
    if resp.parsed_output is None:
        raise RuntimeError(f"synthesis pass returned no parseable result (stop_reason={resp.stop_reason})")
    return PassResult(resp.parsed_output, _raw_text(resp), _usage(resp), latency)


def _raw_text(resp) -> str:
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")


def _usage(resp) -> dict:
    u = resp.usage
    return u.model_dump() if hasattr(u, "model_dump") else dict(u)


def _observe_intro(meta: VideoMeta, description: str, transcript: str | None) -> str:
    lines = [
        f"Video is {meta.duration_s:.1f}s long. Frames below are labelled with their timestamps.",
        f"\nUser's written description of the task:\n{description}",
    ]
    if transcript:
        lines.append(f"\nTranscript of in-video narration:\n{transcript}")
    return "\n".join(lines)


def _synthesis_input(observations: Observations, description: str, transcript: str | None) -> str:
    lines = [f"User's written description of the task:\n{description}"]
    if transcript:
        lines.append(f"\nTranscript of in-video narration:\n{transcript}")
    lines.append(f"\nGrounded observations (JSON):\n{observations.model_dump_json(indent=2)}")
    return "\n".join(lines)
