"""A dependency-free localhost dashboard for MK2's real current state: `morrow demo`.

Standard-library HTTP server only. It shows what actually exists — detected runtime
hardware, the frozen human gold specs, deterministic validation, and any immutable run
artifacts — and never fabricates an end-to-end execution. Status inspection imports no
model weights; the optional live-analysis endpoint is the only path that touches Qwen,
and only when the user asks for it. The dashboard is fully usable without Torch.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .cases import CLIPS, ClipConfig
from .ingest import VideoMeta, probe
from .model import PROMPT_VERSION, prompt_fingerprint
from .qwen import DEFAULT_QWEN_MODEL
from .schemas import WorkflowSpec
from .validate import validate

STATIC = Path(__file__).parent / "demo_static"
# When no real video is on disk we still want the structural gold checks (references,
# evidence, grounded necessity) to run; a huge sentinel duration makes the timestamp
# bounds check a no-op, and we flag that bounds went unchecked.
_SENTINEL_DURATION = 1e9


# --- runtime + status (never loads model weights) ---------------------------

def _runtime() -> dict:
    chip = None
    if platform.system() == "Darwin":
        try:
            chip = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip() or None
        except Exception:
            chip = None
    if not chip:
        chip = platform.processor() or platform.machine() or "unknown"

    torch_installed = importlib.util.find_spec("torch") is not None
    torch_version = None
    mps = cuda = False
    cuda_devices: list[str] = []
    if torch_installed:
        try:
            import torch  # importing torch is fine — it loads no model weights

            torch_version = torch.__version__
            mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
            cuda = bool(torch.cuda.is_available())
            if cuda:
                cuda_devices = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        except Exception as e:  # torch present but broken — report honestly
            torch_version = f"error: {type(e).__name__}: {e}"

    return {
        "chip": chip,
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "torch_installed": torch_installed,
        "torch_version": torch_version,
        "mps_available": mps,
        "cuda_available": cuda,
        "cuda_devices": cuda_devices,
    }


def _checkpoint_local(model: str) -> bool:
    """Does the configured checkpoint appear to be on disk? Filesystem-only, no download."""
    if Path(model).expanduser().is_dir():
        return True
    import os

    roots = []
    if os.environ.get("HF_HUB_CACHE"):
        roots.append(Path(os.environ["HF_HUB_CACHE"]))
    if os.environ.get("HF_HOME"):
        roots.append(Path(os.environ["HF_HOME"]) / "hub")
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    cache_dirname = "models--" + model.replace("/", "--")
    for root in roots:
        try:
            snap = root / cache_dirname / "snapshots"
            if snap.is_dir() and any(snap.iterdir()):
                return True
        except Exception:
            continue
    return False


def _model_status() -> dict:
    model = DEFAULT_QWEN_MODEL
    return {
        "checkpoint": model,
        "available_locally": _checkpoint_local(model),
        "note": "checkpoint presence is a filesystem check only; no weights are loaded or downloaded",
    }


def _validate_spec(spec: WorkflowSpec, video: Path, probe_video: bool) -> tuple[list, bool]:
    meta = VideoMeta(path=str(video), duration_s=_SENTINEL_DURATION, width=0, height=0, fps=0.0)
    bounds_checked = False
    if probe_video and video.is_file():
        try:
            meta = probe(str(video))
            bounds_checked = True
        except Exception:
            pass  # ffprobe missing or unreadable — fall back to structural checks
    return validate(spec, meta), bounds_checked


def _gold_summary(repo_root: Path) -> dict:
    out = {}
    for name, clip in CLIPS.items():
        spec = _load_gold(repo_root, name)
        if spec is None:
            out[name] = {"valid": False, "status": None, "confidence": None, "reason": "gold file missing"}
            continue
        issues, _ = _validate_spec(spec, _video_file(repo_root, clip), probe_video=False)
        out[name] = {
            "valid": not any(i.severity == "error" for i in issues),
            "status": spec.status,
            "confidence": spec.confidence,
        }
    return out


def _pipeline(repo_root: Path, have_runs: bool, gold_ok: bool) -> list:
    pending = "complete" if have_runs else "pending"
    run_note = "" if have_runs else " — no Qwen run yet"
    return [
        {"stage": "Ingest", "state": "ready",
         "detail": "ffprobe metadata + deterministic frame sampling implemented"},
        {"stage": "Observe", "state": pending,
         "detail": f"prompt v0 frozen; produces grounded observations from a Qwen run{run_note}"},
        {"stage": "Synthesize", "state": pending,
         "detail": f"prompt v0 frozen; produces the WorkflowSpec from observations{run_note}"},
        {"stage": "Validate", "state": "ready",
         "detail": f"deterministic validator implemented; frozen gold specs {'valid' if gold_ok else 'INVALID'}"},
    ]


def status_report(repo_root: Path) -> dict:
    gold = _gold_summary(repo_root)
    gold_ok = all(g["valid"] for g in gold.values())
    have_runs = bool(_all_run_dirs(repo_root))
    return {
        "runtime": _runtime(),
        "model": _model_status(),
        "pipeline": _pipeline(repo_root, have_runs, gold_ok),
        "baseline0": {
            "prompt_version": PROMPT_VERSION,
            "prompt_fingerprint": prompt_fingerprint(),
            "gold": gold,
            "runs_present": have_runs,
            "checklist": [
                {"item": "video ingest infrastructure", "done": True},
                {"item": "prompt v0 frozen", "done": True},
                {"item": "three gold specs frozen and valid", "done": gold_ok},
                {"item": "deterministic validation implemented", "done": True},
                {"item": "Qwen Baseline-0 runs completed", "done": have_runs},
            ],
        },
    }


# --- cases + artifacts ------------------------------------------------------

def _video_name(clip: ClipConfig) -> str:
    return clip.video or (clip.source.replace("/", "_") + ".mp4")


def _video_file(repo_root: Path, clip: ClipConfig) -> Path:
    return repo_root / "data" / "videos" / _video_name(clip)


def _load_gold(repo_root: Path, name: str) -> WorkflowSpec | None:
    p = repo_root / "eval" / "gold_workflows" / f"{name}.json"
    return WorkflowSpec.model_validate_json(p.read_text()) if p.is_file() else None


def _all_run_dirs(repo_root: Path) -> list[Path]:
    runs = repo_root / "eval" / "runs"
    if not runs.is_dir():
        return []
    return [d for d in runs.iterdir() if d.is_dir() and (d / "manifest.json").is_file()]


def _find_runs(repo_root: Path, name: str) -> list[dict]:
    runs_dir = repo_root / "eval" / "runs"
    scores_dir = repo_root / "eval" / "scores"
    out = []
    if runs_dir.is_dir():
        for d in sorted(runs_dir.glob(f"{name}-*")):
            manifest_file = d / "manifest.json"
            if not manifest_file.is_file():
                continue
            manifest = json.loads(manifest_file.read_text())
            run_id = manifest.get("run_id", "")
            scores = []
            if scores_dir.is_dir():
                for s in sorted(scores_dir.glob(f"{run_id}__*.json")):
                    scores.append(json.loads(s.read_text()))
            out.append({"run_id": run_id, "dir": str(d.relative_to(repo_root)),
                        "manifest": manifest, "scores": scores})
    return out


def case_payload(repo_root: Path, clip: ClipConfig) -> dict:
    spec = _load_gold(repo_root, clip.name)
    video = _video_file(repo_root, clip)
    issues, bounds = ([], False) if spec is None else _validate_spec(spec, video, probe_video=True)
    return {
        "name": clip.name,
        "role": clip.role,
        "source": clip.source,
        "description": clip.description,
        "video": {"present": video.is_file(), "url": f"/media/{clip.name}", "filename": _video_name(clip)},
        "gold_label": "FROZEN HUMAN GOLD",
        "gold": spec.model_dump() if spec else None,
        "expected": {"status": spec.status if spec else None,
                     "confidence": spec.confidence if spec else None},
        "validation": {
            "parsed": spec is not None,
            "pass": spec is not None and not any(i.severity == "error" for i in issues),
            "bounds_checked": bounds,
            "issues": [{"severity": i.severity, "message": i.message} for i in issues],
        },
        "runs": _find_runs(repo_root, clip.name),
    }


# --- HTTP handler -----------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def repo_root(self) -> Path:
        return self.server.repo_root  # type: ignore[attr-defined]

    def log_message(self, *args):  # keep the console (and test output) quiet
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send_static("index.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return self._send_static("styles.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self._send_static("app.js", "application/javascript; charset=utf-8")
        if path == "/api/status":
            return self._send_json(status_report(self.repo_root))
        if path == "/api/cases":
            return self._send_json([{"name": c.name, "role": c.role} for c in CLIPS.values()])
        if path.startswith("/api/cases/"):
            name = path[len("/api/cases/"):]
            clip = CLIPS.get(name)
            if not clip:
                return self._send_json({"error": f"unknown case {name!r}"}, 404)
            return self._send_json(case_payload(self.repo_root, clip))
        if path.startswith("/media/"):
            return self._serve_media(path[len("/media/"):])
        return self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/analyze":
            return self._send_json({"error": "not found"}, 404)
        return self._analyze()

    # --- endpoints ---

    def _analyze(self):
        body = self._read_json()
        clip = CLIPS.get(body.get("case"))
        if not clip:
            return self._send_json({"error": "unknown or missing case"}, 400)
        video = _video_file(self.repo_root, clip)
        if not video.is_file():
            return self._send_json(
                {"label": "LIVE QWEN OUTPUT", "error": f"video not found: data/videos/{_video_name(clip)}"}, 400)

        model = body.get("model") or None
        try:
            frames = int(body.get("frames") or 8)
        except (TypeError, ValueError):
            frames = 8

        try:
            from .analyze import analyze  # imported lazily; constructs Qwen only here
            from .backend import get_backend

            backend = get_backend("qwen", **({"model": model} if model else {}))
            result = analyze(str(video), clip.description, frames=frames, backend=backend)
            self._send_json({
                "label": "LIVE QWEN OUTPUT",
                "backend": backend.info(),
                "frames": result.frame_timestamps,
                "observations": result.observations.model_dump(),
                "spec": result.spec.model_dump(),
                "validation": [{"severity": i.severity, "message": i.message} for i in result.issues],
                "telemetry": {
                    "observe_latency_s": round(result.obs_pass.latency_s, 3),
                    "synthesize_latency_s": round(result.synth_pass.latency_s, 3),
                    "observe_usage": result.obs_pass.usage,
                    "synthesize_usage": result.synth_pass.usage,
                },
            })
        except Exception as e:
            self._send_json({"label": "LIVE QWEN OUTPUT", "error": f"{type(e).__name__}: {e}"}, 500)

    def _serve_media(self, name: str):
        clip = CLIPS.get(name)
        if not clip:
            return self._send_json({"error": f"unknown case {name!r}"}, 404)
        path = _video_file(self.repo_root, clip)
        if not path.is_file():
            return self._send_json(
                {"error": f"video not found: data/videos/{_video_name(clip)}", "missing": True}, 404)

        size = path.stat().st_size
        rng = self.headers.get("Range")
        if rng:
            span = _parse_range(rng, size)
            if span is None:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = span
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                self._copy(f, end - start + 1)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(path, "rb") as f:
                self._copy(f, size)

    # --- helpers ---

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _send_json(self, obj, code: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, filename: str, content_type: str):
        path = STATIC / filename
        if not path.is_file():
            return self._send_json({"error": f"missing static asset {filename}"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _copy(self, f, length: int):
        remaining = length
        while remaining > 0:
            chunk = f.read(min(1 << 16, remaining))
            if not chunk:
                break
            self.wfile.write(chunk)
            remaining -= len(chunk)


def _parse_range(rng: str, size: int):
    units, _, spec = rng.partition("=")
    if units.strip() != "bytes":
        return None
    start_s, _, end_s = spec.partition("-")
    try:
        if start_s == "":
            if end_s == "":
                return None
            start = max(0, size - int(end_s))
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start > end or start >= size:
        return None
    return start, min(end, size - 1)


# --- server -----------------------------------------------------------------

def _find_repo_root() -> Path:
    for base in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (base / "eval" / "gold_workflows").is_dir():
            return base
    return Path(__file__).resolve().parents[2]


def make_server(host: str, port: int, repo_root) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    server.repo_root = Path(repo_root)  # type: ignore[attr-defined]
    return server


def serve(host: str = "127.0.0.1", port: int = 8000, repo_root=None) -> int:
    root = Path(repo_root) if repo_root else _find_repo_root()
    server = make_server(host, port, root)
    url = f"http://{host}:{port}"
    print(f"morrow demo -> {url}   (repo: {root})")
    print("Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
