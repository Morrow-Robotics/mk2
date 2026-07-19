"""Local Qwen3-VL backend via Transformers — the default MK2 stack.

Unproven on purpose. MK1's frozen POC3 run used the Qwen3-VL 2B model and did badly;
MK2 treats Qwen as a baseline to *measure*, not a capability to assume. Generation is
greedy/deterministic so a run reproduces from its manifest.

Because Qwen has no structured-output API, the target JSON Schema is appended to the
user turn as an instruction; the frozen v0 system prompt is never touched. The output
is parsed with `schema.model_validate_json` — the same contract every backend upholds.

torch/transformers/PIL are imported lazily inside the constructor: importing this module
(or the rest of the package) requires none of them; running Qwen requires local weights
and compute, but no API key.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel

from .backend import Block, Generation, Image, Text

DEFAULT_QWEN_MODEL = os.environ.get("MORROW_QWEN_MODEL", "Qwen/Qwen3-VL-8B-Instruct")


class QwenBackend:
    def __init__(self, model: str | None = None, dtype=None, device: str | None = None,
                 max_new_tokens: int = 8192):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.model_id = model or DEFAULT_QWEN_MODEL
        self.max_new_tokens = max_new_tokens
        self.device = device or _pick_device(torch)
        self.torch_dtype = _pick_dtype(torch, dtype, self.device)
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = AutoModelForImageTextToText.from_pretrained(self.model_id, dtype=self.torch_dtype)
        self.model.to(self.device)
        self.model.eval()
        self._info = self._build_info()

    def info(self) -> dict:
        return dict(self._info)

    def generate(self, *, system: str, content: list[Block], schema: type[BaseModel]) -> Generation:
        import torch

        images, user_content = [], []
        for block in content:
            if isinstance(block, Text):
                user_content.append({"type": "text", "text": block.text})
            else:  # Image
                images.append(_to_pil(block.jpeg))
                user_content.append({"type": "image"})
        user_content.append({"type": "text", "text": _schema_instruction(schema)})

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(
            text=[text], images=images or None, return_tensors="pt"
        ).to(self.device)

        t0 = time.perf_counter()
        with torch.no_grad():
            generated = self.model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False, num_beams=1
            )
        latency = time.perf_counter() - t0

        prompt_len = inputs.input_ids.shape[1]
        new_tokens = generated[0][prompt_len:]
        raw_text = self.processor.decode(new_tokens, skip_special_tokens=True)
        parsed = schema.model_validate_json(_extract_json(raw_text))

        usage = {"input_tokens": int(prompt_len), "output_tokens": int(new_tokens.shape[0])}
        return Generation(parsed=parsed, raw_text=raw_text, usage=usage, latency_s=latency)

    def _build_info(self) -> dict:
        snapshot = _resolve_snapshot_dir(self.model_id, self.model)
        return {
            "backend": "qwen",
            "model": self.model_id,
            "revision": getattr(self.model.config, "_commit_hash", None),
            "device": str(self.device),
            "dtype": str(self.torch_dtype).replace("torch.", ""),
            "quantization": _quantization(self.model),
            # A sampled head/tail fingerprint, not a full-weights digest — named honestly.
            "weight_fingerprint_sha256": _weight_fingerprint(snapshot),
            # Exact runtime the result depends on — reproducibility over loose version bounds.
            "environment": _environment(),
        }


def _environment() -> dict:
    import os
    import platform as pl

    import torch

    def _ver(mod: str):
        try:
            return __import__(mod).__version__
        except Exception:
            return None

    return {
        "torch": torch.__version__,
        "torchvision": _ver("torchvision"),
        "transformers": _ver("transformers"),
        "pillow": _ver("PIL"),
        "accelerate": _ver("accelerate"),
        "python": pl.python_version(),
        "platform": pl.platform(),
        "mac_version": pl.mac_ver()[0] or None,
        "mps_fallback": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"),
    }


def _pick_device(torch) -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _pick_dtype(torch, dtype, device: str):
    if dtype is None:
        return torch.float32 if device == "cpu" else torch.bfloat16
    if isinstance(dtype, str):
        return getattr(torch, dtype)
    return dtype


def _to_pil(jpeg: bytes):
    from PIL import Image as PILImage

    return PILImage.open(io.BytesIO(jpeg)).convert("RGB")


def _schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Return ONLY a single JSON object that validates against this JSON Schema. "
        "No prose, no markdown, no code fences.\n\nJSON Schema:\n"
        + json.dumps(schema.model_json_schema())
    )


def _extract_json(text: str) -> str:
    """Pull the first balanced top-level JSON object out of the model's output.

    String-aware: braces inside string values don't count, so a value like "}" won't
    end the object early. This also transparently handles code fences and surrounding
    prose, since it just scans from the first '{' to its matching '}'.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError(f"unterminated JSON object in model output: {text[start:start + 200]!r}")


def _quantization(model) -> str:
    cfg = getattr(model.config, "quantization_config", None)
    if cfg is None:
        return "none"
    return getattr(cfg, "quant_method", type(cfg).__name__)


def _resolve_snapshot_dir(model_id: str, model) -> Path:
    local = Path(getattr(model.config, "_name_or_path", model_id))
    if local.is_dir():
        return local
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(model_id, local_files_only=True))


def _weight_fingerprint(snapshot: Path) -> str:
    """Content-sensitive fingerprint over the checkpoint's weight shards.

    Sampled (name, size, head, tail) per shard rather than a full multi-GB digest — enough
    to pin identity for provenance and run ids without hashing every byte.
    """
    shards = sorted(snapshot.glob("*.safetensors")) or sorted(snapshot.glob("*.bin"))
    if not shards:
        raise RuntimeError(f"no weight shards under {snapshot} — cannot fingerprint for provenance")
    h = hashlib.sha256()
    for shard in shards:
        size = shard.stat().st_size
        h.update(shard.name.encode())
        h.update(str(size).encode())
        with open(shard, "rb") as f:
            h.update(f.read(1 << 20))
            if size > (1 << 20):
                f.seek(-(1 << 20), io.SEEK_END)
                h.update(f.read(1 << 20))
    return h.hexdigest()
