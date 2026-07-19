"""Run one clip through the pipeline and write an immutable, complete run artifact.

A run is identified by a deterministic id — a hash of the exact inputs (video bytes,
model, prompt version, description, transcript, frame count). Same inputs -> same id,
so a run is never silently redone; if its directory already exists it is left untouched.

Each run directory preserves everything needed to audit or reproduce the result:

    manifest.json        inputs, video hash, frame timestamps, model+prompt version, telemetry
    observation_raw.txt  raw model response, pass 1
    observations.json    parsed observations
    synthesis_raw.txt     raw model response, pass 2
    workflowspec.json    the WorkflowSpec
    validation.json      deterministic validation issues
    scoreboard.json      self metrics, gold metrics (if gold exists), critical checks

Usage:
    ANTHROPIC_API_KEY=... python eval/run.py development --video path/to/office.mp4
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
from morrow import analyze  # noqa: E402
from morrow.model import prompt_fingerprint  # noqa: E402
from morrow.schemas import WorkflowSpec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_ROOT = REPO_ROOT / "eval" / "runs"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_run_id(video_sha: str, description: str, transcript: str | None, frames: int) -> str:
    fp = prompt_fingerprint()
    key = json.dumps({
        "video_sha256": video_sha,
        "model": fp["model"],
        "prompt_version": fp["prompt_version"],
        "description": description,
        "transcript": transcript or "",
        "frames": frames,
    }, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def run_clip(clip, video_path, frames=8, transcript=None, out_root=DEFAULT_OUT_ROOT, client=None) -> dict:
    video_sha = sha256_file(video_path)
    run_id = compute_run_id(video_sha, clip.description, transcript, frames)
    run_dir = Path(out_root) / f"{clip.name}-{run_id}"
    if run_dir.exists():
        return {"run_id": run_id, "dir": run_dir, "skipped": True, "scoreboard": _read_scoreboard(run_dir)}

    result = analyze(video_path, clip.description, transcript=transcript, frames=frames, client=client)

    gold = _load_gold(clip.gold_path)
    has_errors = any(i.severity == "error" for i in result.issues)
    self_m = metrics.self_metrics(result.spec, has_errors)
    gold_m = metrics.gold_metrics(result.spec, gold) if gold else None
    scoreboard = {
        "self": self_m,
        "gold": gold_m,
        "critical_checks": metrics.critical_checks(result.spec, self_m, clip.role, gold_m),
        "gold_present": gold is not None,
    }

    run_dir.mkdir(parents=True)
    _write(run_dir / "manifest.json", _manifest(run_id, clip, video_path, video_sha, transcript, frames, result))
    (run_dir / "observation_raw.txt").write_text(result.obs_pass.raw_json)
    _write(run_dir / "observations.json", result.observations.model_dump())
    (run_dir / "synthesis_raw.txt").write_text(result.synth_pass.raw_json)
    _write(run_dir / "workflowspec.json", result.spec.model_dump())
    _write(run_dir / "validation.json", [asdict(i) for i in result.issues])
    _write(run_dir / "scoreboard.json", scoreboard)

    return {"run_id": run_id, "dir": run_dir, "skipped": False, "scoreboard": scoreboard}


def _manifest(run_id, clip, video_path, video_sha, transcript, frames, result) -> dict:
    return {
        "run_id": run_id,
        "clip": {"name": clip.name, "role": clip.role, "source": clip.source, "description": clip.description},
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
        "prompt_fingerprint": prompt_fingerprint(),
        "telemetry": {
            "observe_latency_s": round(result.obs_pass.latency_s, 3),
            "synthesize_latency_s": round(result.synth_pass.latency_s, 3),
            "observe_usage": result.obs_pass.usage,
            "synthesize_usage": result.synth_pass.usage,
        },
    }


def _load_gold(gold_path: str | None) -> WorkflowSpec | None:
    if not gold_path:
        return None
    p = REPO_ROOT / gold_path
    return WorkflowSpec.model_validate_json(p.read_text()) if p.exists() else None


def _read_scoreboard(run_dir: Path) -> dict | None:
    f = run_dir / "scoreboard.json"
    return json.loads(f.read_text()) if f.exists() else None


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/run.py")
    parser.add_argument("clip", choices=sorted(clips.CLIPS), help="which clip to run")
    parser.add_argument("--video", required=True, help="path to the local video file")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--transcript", help="path to a narration transcript (optional)")
    args = parser.parse_args(argv)

    transcript = Path(args.transcript).read_text() if args.transcript else None
    out = run_clip(clips.CLIPS[args.clip], args.video, frames=args.frames, transcript=transcript)

    tag = "exists (skipped)" if out["skipped"] else "wrote"
    print(f"{tag}: {out['dir']}")
    print(json.dumps(out["scoreboard"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
