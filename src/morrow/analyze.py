"""Orchestration: a video and a description in, a validated WorkflowSpec out.

ingest -> observe -> synthesize -> validate. The `Analysis` keeps the intermediate
observations and the deterministic issues alongside the spec, so a caller can see how
the spec was reached and decide what to do with one that parsed but failed a check.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from .ingest import VideoMeta, probe, sample_frames
from .model import Observations, observe, synthesize
from .schemas import WorkflowSpec
from .validate import Issue, validate


@dataclass
class Analysis:
    meta: VideoMeta
    observations: Observations
    spec: WorkflowSpec
    issues: list[Issue]


def analyze(
    video_path: str,
    description: str,
    transcript: str | None = None,
    frames: int = 8,
    client: anthropic.Anthropic | None = None,
) -> Analysis:
    client = client or anthropic.Anthropic()
    meta = probe(video_path)
    sampled = sample_frames(video_path, meta, frames)
    observations = observe(sampled, meta, description, transcript, client)
    spec = synthesize(observations, description, transcript, client)
    issues = validate(spec, meta)
    return Analysis(meta=meta, observations=observations, spec=spec, issues=issues)
