"""The model-backend boundary.

Two real backends exist — local Qwen (the default, the stack we plan to ship) and
optional Anthropic (a hosted comparison baseline) — so this abstraction earns its keep:
it is the single seam the evaluation swaps to measure one stack against another.

A backend takes a frozen system prompt and a sequence of neutral content blocks (text
and JPEG images), runs the model *deterministically*, and returns a validated instance
of a Pydantic schema plus the telemetry and provenance a run log must preserve. Prompt
v0 and the WorkflowSpec schema live above this line and never change per backend; only
how the schema is elicited (structured-output API vs. an appended instruction) differs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Image:
    jpeg: bytes


Block = Text | Image


@dataclass
class Generation:
    """One model call: the validated object plus everything a run log keeps."""

    parsed: BaseModel
    raw_text: str
    usage: dict
    latency_s: float


class Backend(Protocol):
    def info(self) -> dict:
        """Provenance: backend, model, revision, quantization, weight hash. Goes in every manifest."""
        ...

    def generate(self, *, system: str, content: list[Block], schema: type[BaseModel]) -> Generation:
        ...


def get_backend(name: str | None = None, **kwargs) -> Backend:
    """Construct a backend by name (default from $MORROW_BACKEND, else 'qwen').

    Heavy imports (torch/transformers, anthropic) live inside the backend modules, so
    importing this module stays cheap and dependency-free.
    """
    name = name or os.environ.get("MORROW_BACKEND", "qwen")
    if name == "qwen":
        from .qwen import QwenBackend
        return QwenBackend(**kwargs)
    if name == "anthropic":
        from .anthropic_backend import AnthropicBackend
        return AnthropicBackend(**kwargs)
    raise ValueError(f"unknown backend {name!r} (expected 'qwen' or 'anthropic')")
