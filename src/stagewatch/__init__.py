"""StageWatch: local-first observability for Python data pipelines."""
from .inspection import inspect_value, register_inspector
from .models import Comparison, Finding, RunRecord, StageRecord
from .pipeline import Pipeline, StageContext, stage

__version__ = "0.2.0a1"

__all__ = [
    "Pipeline", "StageContext", "stage", "inspect_value", "register_inspector",
    "Comparison", "Finding", "RunRecord", "StageRecord", "__version__",
]
