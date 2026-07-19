"""Optional Anthropic backend — a hosted comparison baseline, not the default stack.

Kept behind the `morrow[anthropic]` extra and constructed only when explicitly selected
(`MORROW_BACKEND=anthropic` or `get_backend("anthropic")`). Uses the structured-output
API to elicit the schema, so the frozen v0 system prompt is passed through unchanged.
"""

from __future__ import annotations

import base64
import time

from pydantic import BaseModel

from .backend import Block, Generation, Image, Text

DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"


class AnthropicBackend:
    def __init__(self, model: str | None = None, max_tokens: int = 16000):
        import anthropic

        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic()

    def info(self) -> dict:
        return {
            "backend": "anthropic",
            "model": self.model,
            "revision": None,
            "dtype": None,
            "quantization": None,
            "weight_fingerprint_sha256": None,
        }

    def generate(self, *, system: str, content: list[Block], schema: type[BaseModel]) -> Generation:
        blocks = [_translate(b) for b in content]

        t0 = time.perf_counter()
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": blocks}],
            output_format=schema,
        )
        latency = time.perf_counter() - t0
        if resp.parsed_output is None:
            raise RuntimeError(f"anthropic returned no parseable result (stop_reason={resp.stop_reason})")

        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        usage = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
        return Generation(parsed=resp.parsed_output, raw_text=raw, usage=usage, latency_s=latency)


def _translate(block: Block) -> dict:
    if isinstance(block, Text):
        return {"type": "text", "text": block.text}
    return {  # Image
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(block.jpeg).decode("ascii"),
        },
    }
