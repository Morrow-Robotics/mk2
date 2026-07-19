"""End-to-end harness smoke test with a mock client and a synthetic video.

Proves the plumbing — frame sampling, both passes, validation, artifact writing,
deterministic run ids, no-overwrite, and the scoreboard — without touching the network.
The only thing this does not exercise is real model behaviour, which is the point.
"""

import subprocess

from clips import ClipConfig
from run import run_clip
from types import SimpleNamespace

from morrow.model import ObservedEntity, ObservedEvent, Observations
from morrow.schemas import Entity, Evidence, StateFact, Step, WorkflowSpec

OBS = Observations(
    entities=[ObservedEntity(name="mug", description="a mug", role_guess="item", first_seen_s=1.0)],
    events=[ObservedEvent(description="place mug in box", kind="action", start_s=1.0, end_s=2.0, entities=["mug"])],
    narration_claims=[],
    notes="",
)

SPEC = WorkflowSpec(
    task_summary="pack a mug into a box",
    entities=[Entity(id="e1", name="mug", role="item", evidence=[Evidence(source="video", start_s=1.0)])],
    initial_state=[],
    steps=[Step(id="s1", action="place", description="place mug in box", entity_ids=["e1"],
                start_s=1.0, end_s=2.0, evidence=[Evidence(source="video", start_s=1.0, end_s=2.0)], confidence=0.8)],
    final_goals=[StateFact(description="mug is in the box", entity_ids=["e1"],
                           evidence=[Evidence(source="video", start_s=2.0)])],
    ordering=[],
    hard_constraints=[],
    soft_preferences=[],
    unknowns=[],
    confidence=0.8,
    status="accepted",
)


class _Resp:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.content = [SimpleNamespace(type="text", text=parsed.model_dump_json())]
        self.usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 50})
        self.stop_reason = "end_turn"


class _MockClient:
    class messages:  # noqa: N801 — mirrors the SDK's client.messages surface
        @staticmethod
        def parse(*, output_format, **_):
            return _Resp(OBS if output_format is Observations else SPEC)


def _synthetic_video(path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10", str(path)],
        check=True, capture_output=True,
    )


def test_harness_writes_full_artifact_and_is_idempotent(tmp_path):
    video = tmp_path / "synthetic.mp4"
    _synthetic_video(video)
    clip = ClipConfig(name="smoke", role="development", source="test", description="pack it")
    out_root = tmp_path / "runs"

    out = run_clip(clip, str(video), frames=3, out_root=out_root, client=_MockClient())

    assert not out["skipped"]
    for name in ("manifest.json", "observation_raw.txt", "observations.json",
                 "synthesis_raw.txt", "workflowspec.json", "validation.json", "scoreboard.json"):
        assert (out["dir"] / name).exists(), f"missing {name}"

    sb = out["scoreboard"]
    assert sb["self"]["validation_pass"] is True
    assert sb["self"]["evidence_coverage"] == 1.0
    assert sb["critical_checks"]["all_facts_traceable"] is True

    # Deterministic id + no overwrite: a second identical run is skipped.
    again = run_clip(clip, str(video), frames=3, out_root=out_root, client=_MockClient())
    assert again["skipped"] is True
    assert again["run_id"] == out["run_id"]
