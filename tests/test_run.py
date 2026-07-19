"""End-to-end harness smoke test with a mock backend and a synthetic video.

Proves the plumbing — frame sampling, both passes, validation, immutable inference
artifacts, deterministic run ids (including backend provenance), and scoring that is
keyed by gold + metrics version so it never goes stale — without weights or network.
The only thing not exercised is real model behaviour.
"""

import subprocess

from clips import ClipConfig
from run import run_clip, score_run

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
                "dtype": "float32", "quantization": "none", "weight_fingerprint_sha256": "0" * 64}

    def generate(self, *, system, content, schema) -> Generation:
        parsed = OBS if schema is Observations else SPEC
        return Generation(parsed=parsed, raw_text=parsed.model_dump_json(),
                          usage={"input_tokens": 100, "output_tokens": 50}, latency_s=0.0)


def _synthetic_video(path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10", str(path)],
        check=True, capture_output=True,
    )


def _run(tmp_path, clip, **kw):
    video = tmp_path / "synthetic.mp4"
    if not video.exists():
        _synthetic_video(video)
    return run_clip(clip, str(video), frames=3, runs_root=tmp_path / "runs",
                    scores_root=tmp_path / "scores", backend=MockBackend(), **kw)


def test_inference_artifact_is_complete_and_immutable(tmp_path):
    clip = ClipConfig(name="smoke", role="development", source="test", description="pack it")
    out = _run(tmp_path, clip)

    assert not out["inference_skipped"]
    # Run directory holds inference only — no scoreboard (that lives, keyed, under scores/).
    for name in ("manifest.json", "observation_raw.txt", "observations.json",
                 "synthesis_raw.txt", "workflowspec.json", "validation.json"):
        assert (out["dir"] / name).exists(), f"missing {name}"
    assert not (out["dir"] / "scoreboard.json").exists()

    assert out["score_path"].exists()
    sb = out["scoreboard"]
    assert sb["self"]["validation_pass"] is True
    assert sb["critical_checks"]["all_facts_traceable"] is True

    # Second identical run re-uses the immutable inference.
    again = _run(tmp_path, clip)
    assert again["inference_skipped"] is True
    assert again["run_id"] == out["run_id"]


def test_run_id_tracks_backend_provenance(tmp_path):
    clip = ClipConfig(name="smoke", role="development", source="test", description="pack it")

    class OtherWeights(MockBackend):
        def info(self):
            return {**super().info(), "weight_fingerprint_sha256": "f" * 64}

    video = tmp_path / "v.mp4"
    _synthetic_video(video)
    a = run_clip(clip, str(video), frames=3, runs_root=tmp_path / "ra", scores_root=tmp_path / "sa", backend=MockBackend())
    b = run_clip(clip, str(video), frames=3, runs_root=tmp_path / "rb", scores_root=tmp_path / "sb", backend=OtherWeights())
    assert a["run_id"] != b["run_id"]


def test_scoring_is_keyed_by_gold_and_never_stale(tmp_path):
    clip = ClipConfig(name="smoke", role="development", source="test", description="pack it")
    out = _run(tmp_path, clip)  # no gold configured -> "nogold" score
    assert out["gold_sha256"] is None
    assert "__nogold__" in out["score_path"].name

    scores_root = tmp_path / "scores"
    gold = tmp_path / "gold.json"

    gold.write_text(SPEC.model_dump_json())
    first = score_run(out["dir"], gold_path=gold, scores_root=scores_root)
    assert first["gold_sha256"] is not None
    assert first["scoreboard"]["gold_present"] is True

    # Change the gold: a new key, a new file, a fresh score — the old one is not returned.
    changed = SPEC.model_copy(update={"task_summary": "different task"})
    gold.write_text(changed.model_dump_json())
    second = score_run(out["dir"], gold_path=gold, scores_root=scores_root)
    assert second["gold_sha256"] != first["gold_sha256"]
    assert second["score_path"] != first["score_path"]
    assert first["score_path"].exists() and second["score_path"].exists()
