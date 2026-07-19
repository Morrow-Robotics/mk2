"""The localhost dashboard: wiring, endpoints, honest state, and safe boundaries.

Runs a real stdlib server on an ephemeral port and drives it over HTTP. Nothing here
loads Torch or model weights — that path is exercised only by an explicit live request,
which these tests deliberately do not make.
"""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from morrow import demo
from morrow.cases import CLIPS

REPO_ROOT = Path(__file__).resolve().parents[1]


def _serve(repo_root):
    server = demo.make_server("127.0.0.1", 0, repo_root)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@pytest.fixture
def real_server():
    server, base = _serve(REPO_ROOT)
    yield base
    server.shutdown()
    server.server_close()


def test_demo_command_is_wired(monkeypatch):
    from morrow import cli
    from morrow import demo as demomod

    called = {}

    def fake_serve(host, port, *a, **k):
        called["args"] = (host, port)
        return 0

    monkeypatch.setattr(demomod, "serve", fake_serve)
    assert cli.main(["demo", "--port", "0"]) == 0
    assert called["args"] == ("127.0.0.1", 0)


def test_index_and_status_respond(real_server):
    st, _, body = _get(real_server + "/")
    assert st == 200 and b"MK2" in body

    st, _, body = _get(real_server + "/api/status")
    assert st == 200
    data = json.loads(body)
    assert {"runtime", "model", "pipeline", "baseline0"} <= set(data)
    assert isinstance(data["runtime"]["chip"], str) and data["runtime"]["chip"]
    assert data["baseline0"]["prompt_version"] == "v0"


def test_all_three_gold_cases_render(real_server):
    for name in ("development", "holdout", "negative"):
        st, _, body = _get(real_server + f"/api/cases/{name}")
        assert st == 200, name
        c = json.loads(body)
        assert c["gold_label"] == "FROZEN HUMAN GOLD"
        assert c["gold"] is not None
        assert c["validation"]["pass"] is True
        assert c["expected"]["status"] == c["gold"]["status"]


def test_unknown_case_is_404(real_server):
    st, _, _ = _get(real_server + "/api/cases/nope")
    assert st == 404


def test_frozen_gold_parses_and_stays_valid():
    from morrow.ingest import VideoMeta
    from morrow.schemas import WorkflowSpec
    from morrow.validate import validate

    meta = VideoMeta(path="x", duration_s=1e9, width=0, height=0, fps=0.0)
    for name in CLIPS:
        spec = WorkflowSpec.model_validate_json((REPO_ROOT / f"eval/gold_workflows/{name}.json").read_text())
        assert not [i for i in validate(spec, meta) if i.severity == "error"], name


def test_status_does_not_construct_or_load_qwen(monkeypatch):
    import morrow.backend as backend
    import morrow.qwen as qwen

    def forbidden(*a, **k):
        raise AssertionError("status inspection must not build a backend")

    monkeypatch.setattr(backend, "get_backend", forbidden)
    monkeypatch.setattr(qwen.QwenBackend, "__init__", forbidden)

    report = demo.status_report(REPO_ROOT)
    assert report["model"]["checkpoint"]  # checkpoint reported without loading anything
    assert "chip" in report["runtime"]


def test_no_hardcoded_chip_name():
    # Hardware must come from runtime detection — no M1/M5 (or any chip) baked in.
    for rel in ("src/morrow/demo.py", "src/morrow/demo_static/app.js",
                "src/morrow/demo_static/index.html", "src/morrow/demo_static/styles.css"):
        text = (REPO_ROOT / rel).read_text()
        assert "M1" not in text and "M5" not in text, f"{rel} hardcodes a chip name"


def test_missing_video_is_handled(tmp_path):
    server, base = _serve(tmp_path)  # empty repo root: no videos on disk
    try:
        st, _, body = _get(base + "/media/development")
        assert st == 404
        assert json.loads(body).get("missing") is True
    finally:
        server.shutdown()
        server.server_close()
    assert demo.case_payload(tmp_path, CLIPS["development"])["video"]["present"] is False


def test_byte_range_requests(tmp_path):
    # Hermetic: a dummy video file, no ffmpeg needed.
    vids = tmp_path / "data" / "videos"
    vids.mkdir(parents=True)
    data = bytes(range(256)) * 40  # 10240 bytes
    (vids / "pexels_7581335.mp4").write_bytes(data)

    server, base = _serve(tmp_path)
    try:
        st, hdr, body = _get(base + "/media/development", headers={"Range": "bytes=0-99"})
        assert st == 206
        assert hdr.get("Content-Range") == f"bytes 0-99/{len(data)}"
        assert hdr.get("Accept-Ranges") == "bytes"
        assert body == data[:100]

        st, hdr, body = _get(base + "/media/development")
        assert st == 200 and hdr.get("Accept-Ranges") == "bytes" and body == data

        st, _, body = _get(base + "/media/development", headers={"Range": "bytes=-50"})
        assert st == 206 and body == data[-50:]
    finally:
        server.shutdown()
        server.server_close()
