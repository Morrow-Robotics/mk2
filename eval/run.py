"""Run one clip through the pipeline: immutable inference, then keyed scoring.

Inference and scoring are separated on purpose. Inference is a pure function of its
inputs (video bytes, backend provenance, prompt version, description, transcript, frame
count) and is written to an immutable run directory identified by a deterministic
`run_id`; if that directory exists it is never redone.

Scoring is a pure function of a run's WorkflowSpec, the gold spec, and the metrics code.
It is written separately under `eval/scores/`, keyed by `run_id + gold_sha256 +
metrics_version`. So when the gold changes, re-scoring produces a *new* score file —
you can never get a stale scoreboard back for a changed gold.

Inference run directory (`eval/runs/<clip>-<run_id>/`):
    manifest.json  observation_raw.txt  observations.json
    synthesis_raw.txt  workflowspec.json  validation.json

Score file (`eval/scores/<run_id>__<gold>__<metrics_version>.json`):
    run_id, clip, gold_sha256, metrics_version, scoreboard

Usage (local Qwen, no API key — needs weights + compute):
    python eval/run.py development --video data/videos/pexels_7581335.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling modules: clips, metrics

import clips  # noqa: E402
import metrics  # noqa: E402
from morrow import analyze, get_backend  # noqa: E402
from morrow.model import prompt_fingerprint  # noqa: E402
from morrow.schemas import WorkflowSpec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = REPO_ROOT / "eval" / "runs"
SCORES_ROOT = REPO_ROOT / "eval" / "scores"


# --- inference (immutable) --------------------------------------------------

def infer(clip, video_path, frames=8, transcript=None, runs_root=RUNS_ROOT, backend=None) -> dict:
    backend = backend or get_backend()
    provenance = backend.info()
    video_sha = sha256_file(video_path)
    run_id = _run_id(video_sha, provenance, clip.description, transcript, frames)
    run_dir = Path(runs_root) / f"{clip.name}-{run_id}"
    if run_dir.exists():
        return {"run_id": run_id, "dir": run_dir, "inference_skipped": True}

    result = analyze(video_path, clip.description, transcript=transcript, frames=frames, backend=backend)

    run_dir.mkdir(parents=True)
    _write(run_dir / "manifest.json", _manifest(run_id, clip, video_path, video_sha, transcript, frames, provenance, result))
    (run_dir / "observation_raw.txt").write_text(result.obs_pass.raw_text)
    _write(run_dir / "observations.json", result.observations.model_dump())
    (run_dir / "synthesis_raw.txt").write_text(result.synth_pass.raw_text)
    _write(run_dir / "workflowspec.json", result.spec.model_dump())
    _write(run_dir / "validation.json", [asdict(i) for i in result.issues])
    return {"run_id": run_id, "dir": run_dir, "inference_skipped": False}


# --- scoring (keyed, re-computable) -----------------------------------------

def score_run(run_dir, gold_path=None, scores_root=SCORES_ROOT) -> dict:
    """Score an existing run against the current gold. Reads the immutable run, writes
    a score keyed by run_id + gold_sha256 + metrics_version — never mutates the run."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    run_id, clip_meta = manifest["run_id"], manifest["clip"]

    spec = WorkflowSpec.model_validate_json((run_dir / "workflowspec.json").read_text())
    issues = json.loads((run_dir / "validation.json").read_text())
    has_errors = any(i["severity"] == "error" for i in issues)

    gp = Path(gold_path) if gold_path else _gold_path_from_manifest(manifest)
    gold_bytes = gp.read_bytes() if gp and gp.exists() else None
    gold_sha = hashlib.sha256(gold_bytes).hexdigest() if gold_bytes else None
    gold = WorkflowSpec.model_validate_json(gold_bytes) if gold_bytes else None

    self_m = metrics.self_metrics(spec, has_errors)
    gold_m = metrics.gold_metrics(spec, gold) if gold else None
    scoreboard = {
        "self": self_m,
        "gold": gold_m,
        "critical_checks": metrics.critical_checks(spec, self_m, clip_meta["role"], gold_m),
        "gold_present": gold is not None,
    }

    record = {
        "run_id": run_id,
        "clip": clip_meta,
        "gold_sha256": gold_sha,
        "metrics_version": metrics.METRICS_VERSION,
        "scoreboard": scoreboard,
    }
    Path(scores_root).mkdir(parents=True, exist_ok=True)
    gold_key = gold_sha[:12] if gold_sha else "nogold"
    score_path = Path(scores_root) / f"{run_id}__{gold_key}__{metrics.METRICS_VERSION}.json"
    _write(score_path, record)
    return {"score_path": score_path, "gold_sha256": gold_sha, "scoreboard": scoreboard}


def run_clip(clip, video_path, frames=8, transcript=None,
             runs_root=RUNS_ROOT, scores_root=SCORES_ROOT, backend=None) -> dict:
    inf = infer(clip, video_path, frames, transcript, runs_root, backend)
    gp = REPO_ROOT / clip.gold_path if clip.gold_path else None
    sc = score_run(inf["dir"], gold_path=gp, scores_root=scores_root)
    return {**inf, **sc}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_id(video_sha, provenance, description, transcript, frames) -> str:
    key = json.dumps({
        "video_sha256": video_sha,
        "backend": provenance,
        "prompt": prompt_fingerprint(),
        "description": description,
        "transcript": transcript or "",
        "frames": frames,
    }, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _manifest(run_id, clip, video_path, video_sha, transcript, frames, provenance, result) -> dict:
    return {
        "run_id": run_id,
        "clip": {"name": clip.name, "role": clip.role, "source": clip.source,
                 "description": clip.description, "gold_path": clip.gold_path},
        "video": {
            "path": video_path,
            "sha256": video_sha,
            "duration_s": result.meta.duration_s,
            "width": result.meta.width,
            "height": result.meta.height,
            "fps": result.meta.fps,
        },
        "transcript": transcript,
        "frames": frames,
        "frame_timestamps": [round(t, 3) for t in result.frame_timestamps],
        "backend": provenance,
        "prompt_fingerprint": prompt_fingerprint(),
        "telemetry": {
            "observe_latency_s": round(result.obs_pass.latency_s, 3),
            "synthesize_latency_s": round(result.synth_pass.latency_s, 3),
            "observe_usage": result.obs_pass.usage,
            "synthesize_usage": result.synth_pass.usage,
        },
    }


def _gold_path_from_manifest(manifest) -> Path | None:
    rel = manifest["clip"].get("gold_path")
    return (REPO_ROOT / rel) if rel else None


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/run.py")
    parser.add_argument("clip", choices=sorted(clips.CLIPS), help="which clip to run")
    parser.add_argument("--video", required=True, help="path to the local video file")
    parser.add_argument("--backend", choices=["qwen", "anthropic"], help="model backend (default: qwen)")
    parser.add_argument("--model", help="override the backend's model/checkpoint id")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--transcript", help="path to a narration transcript (optional)")
    args = parser.parse_args(argv)

    backend = get_backend(args.backend, **({"model": args.model} if args.model else {}))
    transcript = Path(args.transcript).read_text() if args.transcript else None
    out = run_clip(clips.CLIPS[args.clip], args.video, frames=args.frames, transcript=transcript, backend=backend)

    print(f"run {out['run_id']}: {out['dir']}"
          f"{' (inference skipped)' if out['inference_skipped'] else ''}")
    print(f"score: {out['score_path']}")
    print(json.dumps(out["scoreboard"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
