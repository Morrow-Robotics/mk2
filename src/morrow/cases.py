"""The three Baseline-0 evaluation cases, shared by `eval/` and the demo dashboard.

Hardcoded — there are three, not a config file's worth. Descriptions are deliberately
generic: the text supplies *intent* while the video must supply item identities, the
observed steps, and their sequence. Videos are not committed (see .gitignore); the
`video` field is the expected local filename under `data/videos/`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClipConfig:
    name: str  # also the artifact prefix and dashboard route
    role: str  # development | holdout | negative
    source: str  # stock provider + id
    description: str
    gold_path: str | None = None  # relative to repo root; may not exist yet
    video: str | None = None  # expected filename under data/videos/


CLIPS: dict[str, ClipConfig] = {
    "development": ClipConfig(
        name="development",
        role="development",
        source="pexels/7581335",
        description="Pack the visible office items into the carton and close it.",
        gold_path="eval/gold_workflows/development.json",
        video="pexels_7581335.mp4",
    ),
    "holdout": ClipConfig(
        name="holdout",
        role="holdout",
        source="pexels/7855140",
        description="Pack the product into the carton and close it.",
        gold_path="eval/gold_workflows/holdout.json",
        video="pexels_7855140.mp4",
    ),
    "negative": ClipConfig(
        name="negative",
        role="negative",
        source="mixkit/42119",
        description="Pack the items into the carton and close it.",
        gold_path="eval/gold_workflows/negative.json",
        video="mixkit_42119.mp4",
    ),
}
