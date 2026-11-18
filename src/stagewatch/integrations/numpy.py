"""NumPy integration helpers (install with ``stagewatch[numpy]``)."""
from __future__ import annotations
from typing import Any
from ..inspection import inspect_value


def inspect_array(value: Any, *, deep_scan_limit_bytes: int = 1_000_000) -> dict[str, Any]:
    import numpy  # noqa: F401
    if not isinstance(value, numpy.ndarray):
        raise TypeError("inspect_array expects a numpy.ndarray")
    return inspect_value(value, deep_scan_limit_bytes=deep_scan_limit_bytes)
