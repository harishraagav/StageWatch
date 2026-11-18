"""Pandas integration helpers (install with ``stagewatch[pandas]``)."""
from __future__ import annotations

from typing import Any

from ..inspection import inspect_value


def inspect_frame(value: Any, *, deep_scan_limit_bytes: int = 1_000_000) -> dict[str, Any]:
    import pandas
    if not isinstance(value, (pandas.DataFrame, pandas.Series)):
        raise TypeError("inspect_frame expects a pandas DataFrame or Series")
    return inspect_value(value, deep_scan_limit_bytes=deep_scan_limit_bytes)
