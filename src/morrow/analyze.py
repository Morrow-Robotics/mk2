"""Orchestration: a video and a description in, a validated WorkflowSpec out.

ingest -> observe -> synthesize -> validate. The `Analysis` keeps the two model
passes (with their raw responses, token usage, and latency) and the deterministic
issues alongside the spec, so a run log can preserve exactly how the spec was reached.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from .ingest import VideoMeta, probe, sample_frames
from .model import Observations, PassResult, observe, synthesize
from .schemas import WorkflowSpec
from .validate import Issue, validate


@dataclass
class Analysis:
    meta: VideoMeta
    obs_pass: PassResult
    synth_pass: PassResult
    issues: list[Issue]
    frame_timestamps: list[float]

    @property
    def observations(self) -> Observations:
        return self.obs_pass.parsed

    @property
    def spec(self) -> WorkflowSpec:
        return self.synth_pass.parsed


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
    obs_pass = observe(sampled, meta, description, transcript, client)
    synth_pass = synthesize(obs_pass.parsed, description, transcript, client)
    issues = validate(synth_pass.parsed, meta)
    return Analysis(
        meta=meta,
        obs_pass=obs_pass,
        synth_pass=synth_pass,
        issues=issues,
        frame_timestamps=[f.timestamp_s for f in sampled],
    )
