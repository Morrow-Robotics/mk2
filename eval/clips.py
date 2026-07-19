"""The three Baseline-0 clips. Hardcoded — there are three, not a config-file's worth.

Descriptions are deliberately generic: the text supplies *intent* while the video must
supply the item identities, the observed steps, and their sequence. The office clip's
description is the one specified for Baseline-0; the other two follow the same pattern.

Videos are not committed (see .gitignore) — Pexels/Mixkit block scripted download, so
the files must be provided locally. `source` records where each clip came from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClipConfig:
    name: str  # also the artifact prefix
    role: str  # development | holdout | negative
    source: str  # stock provider + id
    description: str
    gold_path: str | None = None  # relative to repo root; may not exist yet


CLIPS: dict[str, ClipConfig] = {
    "development": ClipConfig(
        name="development",
        role="development",
        source="pexels/7581335",
        description="Pack the visible office items into the carton and close it.",
        gold_path="eval/gold_workflows/development.json",
    ),
    "holdout": ClipConfig(
        name="holdout",
        role="holdout",
        source="pexels/7855140",
        description="Pack the product into the carton and close it.",
        gold_path="eval/gold_workflows/holdout.json",
    ),
    "negative": ClipConfig(
        name="negative",
        role="negative",
        source="mixkit/42119",
        description="Pack the items into the carton and close it.",
        gold_path="eval/gold_workflows/negative.json",
    ),
}
