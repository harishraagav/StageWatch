"""Safe, bounded metadata inspection without mandatory third-party dependencies."""
from __future__ import annotations

import math
import statistics
import sys
from collections.abc import Callable, Mapping
from typing import Any

_INSPECTORS: list[tuple[Callable[[Any], bool], Callable[[Any, int], dict[str, Any]]]] = []


def register_inspector(predicate: Callable[[Any], bool], inspector: Callable[[Any, int], dict[str, Any]]) -> None:
    """Register a custom inspector. New inspectors are checked before built-ins."""
    if not callable(predicate) or not callable(inspector):
        raise TypeError("predicate and inspector must be callable")
    _INSPECTORS.insert(0, (predicate, inspector))


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _deep_size(value: Any, seen: set[int] | None = None, depth: int = 0) -> int:
    if seen is None:
        seen = set()
    ident = id(value)
    if ident in seen or depth > 5:
        return 0
    seen.add(ident)
    size = sys.getsizeof(value, 0)
    if isinstance(value, Mapping):
        for key, item in list(value.items())[:1000]:
            size += _deep_size(key, seen, depth + 1) + _deep_size(item, seen, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in list(value)[:1000]:
            size += _deep_size(item, seen, depth + 1)
    return size


def _numeric_summary(numbers: list[float], multiplier: float = 1.5) -> dict[str, Any]:
    """Summarize finite values and Tukey-IQR outliers; never return raw values."""
    if not numbers:
        return {"numeric_count": 0, "outlier_count": 0, "outlier_ratio": 0.0}
    ordered = sorted(numbers)
    count = len(ordered)

    def percentile(fraction: float) -> float:
        if count == 1:
            return ordered[0]
        position = (count - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, count - 1)
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    q1 = percentile(0.25)
    median = percentile(0.5)
    q3 = percentile(0.75)
    iqr = q3 - q1
    low_fence = q1 - multiplier * iqr
    high_fence = q3 + multiplier * iqr
    outliers = sum(value < low_fence or value > high_fence for value in ordered) if iqr > 0 else sum(value != median for value in ordered)
    mean = math.fsum(ordered) / count
    std = statistics.pstdev(ordered) if count > 1 else 0.0
    return {
        "numeric_count": count,
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "mean": mean,
        "std": std,
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "outlier_count": outliers,
        "outlier_ratio": outliers / count,
        "outlier_lower_fence": low_fence,
        "outlier_upper_fence": high_fence,
    }


def _infer_builtin_shape(value: Any, *, max_depth: int = 8, max_items: int = 10000) -> list[int] | None:
    """Infer a rectangular nested list/tuple shape without copying its payload."""
    if not isinstance(value, (list, tuple)):
        return None
    current = [value]
    shape: list[int] = []
    inspected = 0
    for _ in range(max_depth):
        lengths = []
        children: list[Any] = []
        sequence_flags: list[bool] = []
        for node in current:
            if isinstance(node, (list, tuple)):
                lengths.append(len(node))
                inspected += len(node)
                if inspected > max_items:
                    return None
                children.extend(node)
                sequence_flags.extend(isinstance(item, (list, tuple)) for item in node)
            else:
                return shape or None
        if not lengths or len(set(lengths)) != 1:
            return None
        shape.append(lengths[0])
        if not children or not any(sequence_flags):
            return shape
        if not all(sequence_flags):
            return None
        current = children
    return shape


def _walk_builtin(value: Any, limit: int = 10000, outlier_iqr_multiplier: float = 1.5) -> dict[str, Any]:
    numeric: list[float] = []
    nan_count = inf_count = none_count = visited = 0
    stack = [(value, 0)]
    while stack and visited < limit:
        item, depth = stack.pop()
        visited += 1
        if item is None:
            none_count += 1
        elif isinstance(item, bool):
            numeric.append(float(item))
        elif isinstance(item, (int, float)):
            number = float(item)
            if math.isnan(number):
                nan_count += 1
            elif math.isinf(number):
                inf_count += 1
            else:
                numeric.append(number)
        elif depth < 5 and isinstance(item, Mapping):
            stack.extend((v, depth + 1) for v in list(item.values())[:limit])
        elif depth < 5 and isinstance(item, (list, tuple, set, frozenset)):
            stack.extend((v, depth + 1) for v in list(item)[:limit])
    result: dict[str, Any] = {
        "nan_count": nan_count,
        "inf_count": inf_count,
        "none_count": none_count,
        "scan_truncated": bool(stack),
    }
    result.update(_numeric_summary(numeric, outlier_iqr_multiplier))
    return result


def _inspect_numpy(value: Any, deep_scan_limit_bytes: int, outlier_iqr_multiplier: float) -> dict[str, Any]:
    import numpy as np

    result: dict[str, Any] = {
        "shape": [int(x) for x in value.shape],
        "dtype": str(value.dtype),
        "estimated_size_bytes": int(value.nbytes),
        "length": int(value.size),
        "empty": bool(value.size == 0),
    }
    if value.dtype.kind in "biuf" and value.nbytes <= deep_scan_limit_bytes:
        try:
            result["nan_count"] = int(np.isnan(value).sum())
            result["inf_count"] = int(np.isinf(value).sum())
            finite = value[np.isfinite(value)]
            result.update(_numeric_summary([float(x) for x in finite.ravel().tolist()], outlier_iqr_multiplier))
        except (TypeError, ValueError, FloatingPointError, OverflowError):
            result["scan_skipped"] = "numeric summary could not be computed"
    else:
        result["scan_skipped"] = "array exceeds scan limit or is non-real numeric"
    return result


def _inspect_pandas(value: Any, deep_scan_limit_bytes: int, outlier_iqr_multiplier: float) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    shape = [int(x) for x in value.shape]
    memory_value = value.memory_usage(index=True, deep=False)
    memory = int(memory_value.sum() if hasattr(memory_value, "sum") else memory_value)
    dtype_value = getattr(value, "dtypes", None)
    dtype_summary = (
        [str(x) for x in dtype_value]
        if dtype_value is not None and not isinstance(dtype_value, str) and hasattr(dtype_value, "__iter__")
        else str(getattr(value, "dtype", dtype_value))
    )
    result: dict[str, Any] = {
        "shape": shape,
        "dtype": dtype_summary,
        "estimated_size_bytes": memory,
        "length": len(value),
        "empty": bool(value.empty),
    }
    if memory <= deep_scan_limit_bytes:
        try:
            missing = value.isna().sum()
            result["missing_count"] = int(missing.sum() if hasattr(missing, "sum") else missing)
            if isinstance(value, pd.DataFrame):
                numeric = value.select_dtypes(include=["number"])
                series_items = [(str(column)[:100], numeric[column]) for column in numeric.columns]
            elif pd.api.types.is_numeric_dtype(value.dtype):
                series_items = [(str(value.name or "value")[:100], value)]
            else:
                series_items = []

            column_summaries: dict[str, Any] = {}
            all_finite: list[float] = []
            all_nan = all_inf = outlier_count = 0
            for column_name, series in series_items:
                array = series.to_numpy(dtype=float, na_value=float("nan"), copy=False).ravel()
                nan_count = int(np.isnan(array).sum())
                inf_count = int(np.isinf(array).sum())
                finite = array[np.isfinite(array)]
                column_summary = _numeric_summary(finite.tolist(), outlier_iqr_multiplier)
                column_summary["nan_count"] = nan_count
                column_summary["inf_count"] = inf_count
                column_summaries[column_name] = column_summary
                all_finite.extend(float(item) for item in finite.tolist())
                all_nan += nan_count
                all_inf += inf_count
                outlier_count += int(column_summary.get("outlier_count", 0))

            result["nan_count"] = all_nan
            result["inf_count"] = all_inf
            result["numeric_columns"] = column_summaries
            result.update(_numeric_summary(all_finite, outlier_iqr_multiplier))
            # For tabular data, count outliers within each numeric column rather
            # than flattening unrelated columns onto one common value scale.
            result["outlier_count"] = outlier_count
            result["outlier_ratio"] = outlier_count / max(1, sum(int(item["numeric_count"]) for item in column_summaries.values()))
        except (TypeError, ValueError, OverflowError):
            result["scan_skipped"] = "tabular numeric summary could not be computed"
    else:
        result["scan_skipped"] = "tabular data exceeds scan limit"
    return result


def _inspect_torch(value: Any, deep_scan_limit_bytes: int, inspect_gpu: bool, outlier_iqr_multiplier: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "shape": [int(x) for x in value.shape],
        "dtype": str(value.dtype),
        "device": str(value.device),
        "length": int(value.numel()),
        "estimated_size_bytes": int(value.numel() * value.element_size()),
        "empty": bool(value.numel() == 0),
    }
    should_scan = result["estimated_size_bytes"] <= deep_scan_limit_bytes and (str(value.device) == "cpu" or inspect_gpu)
    if should_scan and (getattr(value, "is_floating_point", lambda: False)() or getattr(value, "is_complex", lambda: False)()):
        try:
            detached = value.detach()
            result["nan_count"] = int(detached.isnan().sum().item())
            result["inf_count"] = int(detached.isinf().sum().item())
            finite = detached[detached.isfinite()]
            if finite.numel() and not getattr(value, "is_complex", lambda: False)():
                result.update(_numeric_summary([float(x) for x in finite.float().reshape(-1).tolist()], outlier_iqr_multiplier))
        except Exception:
            result["scan_skipped"] = "tensor scan was unavailable"
    elif result["estimated_size_bytes"] > deep_scan_limit_bytes:
        result["scan_skipped"] = "tensor exceeds scan limit"
    elif str(value.device) != "cpu":
        result["scan_skipped"] = "GPU scanning is disabled by default"
    return result


def inspect_value(
    value: Any, *, deep_scan_limit_bytes: int = 1_000_000, inspect_gpu: bool = False,
    outlier_iqr_multiplier: float = 1.5,
) -> dict[str, Any]:
    """Return metadata and safe numerical summaries; never return raw user data."""
    if deep_scan_limit_bytes < 0:
        raise ValueError("deep_scan_limit_bytes must be >= 0")
    if outlier_iqr_multiplier <= 0:
        raise ValueError("outlier_iqr_multiplier must be > 0")
    result: dict[str, Any] = {"type": f"{type(value).__module__}.{type(value).__qualname__}"}
    if value is None:
        result.update({"estimated_size_bytes": sys.getsizeof(None), "length": None, "empty": True, "none_count": 1})
    elif isinstance(value, (str, bytes, bytearray)):
        result.update({"length": len(value), "empty": len(value) == 0, "estimated_size_bytes": sys.getsizeof(value)})
    elif isinstance(value, (bool, int, float)):
        result.update({"length": None, "empty": False, "estimated_size_bytes": sys.getsizeof(value)})
        result.update(_walk_builtin(value, outlier_iqr_multiplier=outlier_iqr_multiplier))
    elif isinstance(value, Mapping):
        keys = list(value.keys())
        result.update({
            "length": len(value), "empty": len(value) == 0,
            "estimated_size_bytes": _deep_size(value),
            "mapping_keys": [str(key)[:100] for key in keys[:50]],
            "mapping_key_count": len(keys),
        })
        walked = _walk_builtin(value, outlier_iqr_multiplier=outlier_iqr_multiplier)
        result.update(walked)
        # Numeric dictionary fields often have unrelated units (e.g. image
        # width, channel count and luminance). Never apply one IQR fence to
        # values from different keys. Analyse numeric vectors per field.
        numeric_fields: dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            if isinstance(item, (list, tuple)) and item and all(
                element is None or isinstance(element, (bool, int, float)) for element in item[:10000]
            ):
                field_summary = _walk_builtin(item, outlier_iqr_multiplier=outlier_iqr_multiplier)
                if int(field_summary.get("numeric_count", 0)) >= 2:
                    numeric_fields[str(key)[:100]] = field_summary
        result["numeric_fields"] = numeric_fields
        if numeric_fields:
            numeric_total = sum(int(item.get("numeric_count", 0)) for item in numeric_fields.values())
            outlier_total = sum(int(item.get("outlier_count", 0)) for item in numeric_fields.values())
            result["outlier_count"] = outlier_total
            result["outlier_ratio"] = outlier_total / max(1, numeric_total)
        else:
            # Scalars from distinct keys may not share a meaningful scale.
            result["outlier_count"] = 0
            result["outlier_ratio"] = 0.0
    elif isinstance(value, (list, tuple, set, frozenset)):
        result.update({"length": len(value), "empty": len(value) == 0, "estimated_size_bytes": _deep_size(value)})
        if isinstance(value, (list, tuple)):
            inferred_shape = _infer_builtin_shape(value)
            if inferred_shape is not None:
                result["shape"] = inferred_shape
        result.update(_walk_builtin(value, outlier_iqr_multiplier=outlier_iqr_multiplier))
    elif type(value).__module__.startswith("numpy") and hasattr(value, "shape") and hasattr(value, "nbytes"):
        result.update(_inspect_numpy(value, deep_scan_limit_bytes, outlier_iqr_multiplier))
    elif type(value).__module__.startswith("pandas") and hasattr(value, "memory_usage"):
        result.update(_inspect_pandas(value, deep_scan_limit_bytes, outlier_iqr_multiplier))
    elif type(value).__module__.startswith("torch") and hasattr(value, "numel") and hasattr(value, "element_size"):
        result.update(_inspect_torch(value, deep_scan_limit_bytes, inspect_gpu, outlier_iqr_multiplier))
    else:
        for predicate, inspector in tuple(_INSPECTORS):
            try:
                if predicate(value):
                    result.update(inspector(value, deep_scan_limit_bytes))
                    break
            except Exception as exc:
                result["custom_inspector_error"] = type(exc).__name__
        else:
            shape = getattr(value, "shape", None)
            if shape is not None:
                try:
                    result["shape"] = [int(x) for x in shape]
                except Exception:
                    result["shape"] = repr(shape)
            dtype = getattr(value, "dtype", None)
            if dtype is not None:
                result["dtype"] = str(dtype)
            nbytes = _safe_int(getattr(value, "nbytes", None))
            result["estimated_size_bytes"] = nbytes if nbytes is not None else _deep_size(value)
            try:
                result["length"] = len(value)
                result["empty"] = len(value) == 0
            except Exception:
                result["length"] = None
                result["empty"] = False
    result.setdefault("estimated_size_bytes", _deep_size(value))
    result.setdefault("length", None)
    result.setdefault("empty", False)
    return result
