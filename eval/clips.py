"""Compatibility shim. The case definitions moved to `morrow.cases` so the eval harness
and the demo dashboard share one source; existing `import clips` / `from clips import ...`
call sites keep working via these re-exports."""

from morrow.cases import CLIPS, ClipConfig

__all__ = ["CLIPS", "ClipConfig"]
