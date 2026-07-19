"""End-to-end harness smoke test with a mock backend and a synthetic video.

Proves the plumbing — frame sampling, both passes, validation, artifact writing,
deterministic run ids (including backend provenance), no-overwrite, and the scoreboard —
without weights or network. The only thing not exercised is real model behaviour.
"""

import subprocess

from clips import ClipConfig
from run import run_clip

from morrow.backend import Generation
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


class MockBackend:
    """A Backend that returns canned observations then spec, with plausible provenance."""

    def info(self) -> dict:
        return {"backend": "mock", "model": "mock-1", "revision": "r0",
                "dtype": "float32", "quantization": "none", "weight_sha256": "0" * 64}

    def generate(self, *, system, content, schema) -> Generation:
        parsed = OBS if schema is Observations else SPEC
        return Generation(parsed=parsed, raw_text=parsed.model_dump_json(),
                          usage={"input_tokens": 100, "output_tokens": 50}, latency_s=0.0)


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

    out = run_clip(clip, str(video), frames=3, out_root=out_root, backend=MockBackend())

    assert not out["skipped"]
    for name in ("manifest.json", "observation_raw.txt", "observations.json",
                 "synthesis_raw.txt", "workflowspec.json", "validation.json", "scoreboard.json"):
        assert (out["dir"] / name).exists(), f"missing {name}"

    sb = out["scoreboard"]
    assert sb["self"]["validation_pass"] is True
    assert sb["self"]["evidence_coverage"] == 1.0
    assert sb["critical_checks"]["all_facts_traceable"] is True

    # Deterministic id + no overwrite: a second identical run is skipped.
    again = run_clip(clip, str(video), frames=3, out_root=out_root, backend=MockBackend())
    assert again["skipped"] is True
    assert again["run_id"] == out["run_id"]


def test_run_id_tracks_backend_provenance(tmp_path):
    # Different weights (different provenance) must yield a different run id.
    video = tmp_path / "synthetic.mp4"
    _synthetic_video(video)
    clip = ClipConfig(name="smoke", role="development", source="test", description="pack it")

    class OtherWeights(MockBackend):
        def info(self):
            return {**super().info(), "weight_sha256": "f" * 64}

    a = run_clip(clip, str(video), frames=3, out_root=tmp_path / "a", backend=MockBackend())
    b = run_clip(clip, str(video), frames=3, out_root=tmp_path / "b", backend=OtherWeights())
    assert a["run_id"] != b["run_id"]
