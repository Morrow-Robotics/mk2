"""Video ingest: probe metadata and sample frames. A thin wrapper over ffmpeg/ffprobe.

Rewritten from scratch rather than ported from MK1 — the job is <100 lines of shelling
out, and copying MK1's version would drag in its provenance and frozen-artifact coupling.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMeta:
    path: str
    duration_s: float
    width: int
    height: int
    fps: float


@dataclass(frozen=True)
class Frame:
    timestamp_s: float
    jpeg: bytes


def _require(tool: str) -> None:
    if shutil.which(tool) is None:
        raise RuntimeError(f"{tool} not found on PATH — install ffmpeg to use morrow ingest")


def probe(path: str) -> VideoMeta:
    """Read duration, dimensions, and frame rate from a video file via ffprobe."""
    _require("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path!r}: {out.stderr.strip()}")

    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError(f"no video stream in {path!r}")

    return VideoMeta(
        path=path,
        duration_s=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=_parse_fraction(video.get("r_frame_rate", "0/1")),
    )


def sample_frames(path: str, meta: VideoMeta, n: int = 8) -> list[Frame]:
    """Extract `n` JPEG frames evenly spread across the clip, each with its timestamp.

    Frames are sampled at the midpoint of `n` equal slices, so the first and last
    moments of the clip are never over-weighted.
    """
    _require("ffmpeg")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    frames = []
    for i in range(n):
        t = meta.duration_s * (i + 0.5) / n
        frames.append(Frame(timestamp_s=t, jpeg=_extract_frame(path, t)))
    return frames


def _extract_frame(path: str, t: float) -> bytes:
    # -ss before -i is an input seek: fast, and accurate enough at demo timescales.
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-ss", f"{t:.3f}", "-i", path,
         "-frames:v", "1", "-q:v", "3", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True,
    )
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"ffmpeg failed to extract frame at t={t:.3f}s: {out.stderr.decode().strip()}")
    return out.stdout


def _parse_fraction(value: str) -> float:
    num, _, den = value.partition("/")
    den_f = float(den) if den else 1.0
    return float(num) / den_f if den_f else 0.0
