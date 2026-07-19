"""MK2: film a demo, describe what you want, get an evidence-backed WorkflowSpec.

The public surface is deliberately small: `analyze` runs the pipeline, `WorkflowSpec`
is what it produces, `validate` checks one, `get_backend` selects the model stack
(local Qwen by default). Everything else is an implementation detail.
"""

from .analyze import Analysis, analyze
from .backend import Backend, get_backend
from .ingest import VideoMeta
from .schemas import WorkflowSpec
from .validate import Issue, validate

__all__ = [
    "analyze", "Analysis", "WorkflowSpec", "VideoMeta",
    "validate", "Issue", "get_backend", "Backend",
]
