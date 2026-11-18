"""Pipeline tracking, anomaly analysis, contracts, comparisons and reporting."""
from __future__ import annotations

import contextvars
import functools
import statistics
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .history import HistoryStore
from .inspection import inspect_value
from .models import Comparison, Finding, RunRecord, StageRecord

_ACTIVE: contextvars.ContextVar["_RunContext | None"] = contextvars.ContextVar("stagewatch_active_run", default=None)
_SCHEMA_FIELDS = ("type", "dtype", "shape", "mapping_keys")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower() or "pipeline"


def _changed_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changed = [field for field in _SCHEMA_FIELDS if old.get(field) != new.get(field)]
    # Length is redundant with shape for array-like objects, but remains useful
    # for built-in containers that have no explicit shape.
    if "shape" not in old and "shape" not in new and old.get("length") != new.get("length"):
        changed.append("length")
    return changed


def _shape_matches(actual: Any, expected: tuple[int | None, ...]) -> bool:
    if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
        return False
    return all(wanted is None or got == wanted for got, wanted in zip(actual, expected))


def _shape_contract_allows_change(
    old_summary: dict[str, Any], new_summary: dict[str, Any], contract: tuple[int | None, ...] | None
) -> bool:
    if contract is None:
        return False
    old_shape, new_shape = old_summary.get("shape"), new_summary.get("shape")
    if old_shape == new_shape:
        return False
    return _shape_matches(old_shape, contract) and _shape_matches(new_shape, contract)


@dataclass
class _Check:
    stage: str | None
    function: Callable[[Any], Any]
    message: str
    severity: str
    target: str
    code: str


@dataclass
class _RunContext:
    pipeline: "Pipeline"
    run: RunRecord
    started_perf: float
    baseline_runs: list[RunRecord] = field(default_factory=list)
    root_cause_stage: str | None = None
    root_cause_message: str | None = None
    active_anomalies: dict[str, int] = field(default_factory=dict)
    accepted_dynamic_source: str | None = None

    @property
    def previous(self) -> RunRecord | None:
        return self.baseline_runs[0] if self.baseline_runs else None


class StageContext:
    """Context-manager object returned by :meth:`Pipeline.stage`."""
    def __init__(self, pipeline: "Pipeline", name: str, input_data: Any = None, has_input: bool = False) -> None:
        self.pipeline = pipeline
        self.name = name
        self.input_data = input_data
        self.has_input = has_input
        self.output_data: Any = None
        self.has_output = False
        self._started = 0.0
        self._started_at = ""
        self._ctx: _RunContext | None = None
        self._token: contextvars.Token | None = None
        self._owns_run = False

    def set_output(self, value: Any) -> Any:
        self.output_data = value
        self.has_output = True
        return value

    def __enter__(self) -> "StageContext":
        active = _ACTIVE.get()
        if active is None or active.pipeline is not self.pipeline:
            self._ctx = self.pipeline._new_context()
            self._token = _ACTIVE.set(self._ctx)
            self._owns_run = True
        else:
            self._ctx = active
        self._started = time.perf_counter()
        self._started_at = _now()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        assert self._ctx is not None
        record = StageRecord(
            name=self.name,
            status="failed" if exc is not None else "success",
            started_at=self._started_at,
            finished_at=_now(),
            duration_ms=(time.perf_counter() - self._started) * 1000,
            input_summary=inspect_value(
                self.input_data,
                deep_scan_limit_bytes=self.pipeline.deep_scan_limit_bytes,
                inspect_gpu=self.pipeline.inspect_gpu,
                outlier_iqr_multiplier=self.pipeline.outlier_iqr_multiplier,
            ) if self.has_input else {},
            output_summary=inspect_value(
                self.output_data,
                deep_scan_limit_bytes=self.pipeline.deep_scan_limit_bytes,
                inspect_gpu=self.pipeline.inspect_gpu,
                outlier_iqr_multiplier=self.pipeline.outlier_iqr_multiplier,
            ) if self.has_output else {},
            error_type=type(exc).__name__ if exc is not None else None,
            error_message=str(exc)[:1000] if exc is not None else None,
        )
        self.pipeline._analyze_record(record, self._ctx)
        self.pipeline._apply_live_checks(
            record,
            self.input_data if self.has_input else None,
            self.output_data if self.has_output else None,
        )
        self.pipeline._finalize_stage_status(record)
        self._ctx.run.stages.append(record)
        if exc is not None:
            self._ctx.run.status = "failed"
        if self._owns_run:
            self.pipeline._finish_context(self._ctx)
            if self._token is not None:
                _ACTIVE.reset(self._token)
        return False


class Pipeline:
    """Observe a sequential pipeline of Python functions.

    StageWatch persists metadata, numerical summaries and findings, never raw
    inputs or outputs. User-provided run metadata is persisted as supplied.
    """
    def __init__(
        self,
        name: str = "default",
        *,
        storage_dir: str | Path | None = ".stagewatch",
        history: bool = True,
        max_history: int = 1000,
        deep_scan_limit_bytes: int = 1_000_000,
        inspect_gpu: bool = False,
        size_change_threshold: float | None = 1.0,
        slowdown_threshold: float | None = 1.0,
        performance_window: int = 5,
        performance_min_samples: int = 3,
        performance_min_duration_ms: float = 5.0,
        performance_comparison_threshold: float = 0.10,
        detect_outliers: bool = True,
        outlier_iqr_multiplier: float = 1.5,
        outlier_min_count: int = 3,
        outlier_min_ratio: float = 0.01,
        distribution_shift_threshold: float | None = 3.0,
        distribution_min_samples: int = 3,
        aggregate_upstream_changes: bool = True,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Pipeline name must be a non-empty string")
        if deep_scan_limit_bytes < 0:
            raise ValueError("deep_scan_limit_bytes must be >= 0")
        if size_change_threshold is not None and size_change_threshold < 0:
            raise ValueError("size_change_threshold must be >= 0 or None")
        if slowdown_threshold is not None and slowdown_threshold < 0:
            raise ValueError("slowdown_threshold must be >= 0 or None")
        if performance_window < 1 or performance_min_samples < 1:
            raise ValueError("performance_window and performance_min_samples must be >= 1")
        if performance_min_duration_ms < 0 or performance_comparison_threshold < 0:
            raise ValueError("performance duration and comparison thresholds must be >= 0")
        if outlier_iqr_multiplier <= 0 or outlier_min_count < 1 or not 0 <= outlier_min_ratio <= 1:
            raise ValueError("Invalid outlier detection configuration")
        if distribution_shift_threshold is not None and distribution_shift_threshold <= 0:
            raise ValueError("distribution_shift_threshold must be > 0 or None")
        if distribution_min_samples < 2:
            raise ValueError("distribution_min_samples must be >= 2")

        self.name = name.strip()
        self.deep_scan_limit_bytes = int(deep_scan_limit_bytes)
        self.inspect_gpu = bool(inspect_gpu)
        self.size_change_threshold = size_change_threshold
        self.slowdown_threshold = slowdown_threshold
        self.performance_window = int(performance_window)
        self.performance_min_samples = int(performance_min_samples)
        self.performance_min_duration_ms = float(performance_min_duration_ms)
        self.performance_comparison_threshold = float(performance_comparison_threshold)
        self.detect_outliers = bool(detect_outliers)
        self.outlier_iqr_multiplier = float(outlier_iqr_multiplier)
        self.outlier_min_count = int(outlier_min_count)
        self.outlier_min_ratio = float(outlier_min_ratio)
        self.distribution_shift_threshold = distribution_shift_threshold
        self.distribution_min_samples = int(distribution_min_samples)
        self.aggregate_upstream_changes = bool(aggregate_upstream_changes)
        self.max_history = max(1, int(max_history))
        self._stages: list[tuple[str, Callable[..., Any]]] = []
        self._checks: list[_Check] = []
        self._shape_contracts: dict[tuple[str, str], tuple[int | None, ...]] = {}
        self._last_run: RunRecord | None = None
        self._memory_history: list[RunRecord] = []
        self.history_enabled = bool(history and storage_dir is not None)
        self.storage_dir = Path(storage_dir).expanduser() if storage_dir is not None else None
        self.db_path = (self.storage_dir / f"{_slug(self.name)}.sqlite3") if self.history_enabled else None
        self._store = HistoryStore(self.db_path, max_history=max_history) if self.db_path else None

    def add_stage(self, function: Callable[..., Any], name: str | None = None) -> Callable[..., Any]:
        """Register a stage function and return a tracked callable."""
        if not callable(function):
            raise TypeError("stage must be callable")
        stage_name = name or function.__name__
        if any(existing == stage_name for existing, _ in self._stages):
            raise ValueError(f"Stage {stage_name!r} is already registered")

        @functools.wraps(function)
        def tracked(*args: Any, **kwargs: Any) -> Any:
            active = _ACTIVE.get()
            if active is not None and active.pipeline is self:
                return self._execute_stage(stage_name, function, *args, **kwargs)
            return self._run_single_stage(stage_name, function, *args, **kwargs)

        self._stages.append((stage_name, tracked))
        return tracked

    def stage_decorator(self, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Return a decorator bound to this pipeline."""
        def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
            return self.add_stage(function, name=name)
        return decorator

    def stage(self, name: str, input_data: Any = None, *, has_input: bool = True) -> StageContext:
        """Create a context-managed stage: ``with pipeline.stage('load') as s:``."""
        return StageContext(self, name, input_data=input_data, has_input=has_input)

    def record_stage(
        self, name: str, input_data: Any, output_data: Any, *, duration_ms: float | None = None
    ) -> StageRecord:
        """Manually record a completed stage without wrapping its function."""
        active = _ACTIVE.get()
        owns = active is None or active.pipeline is not self
        token = None
        if owns:
            active = self._new_context()
            token = _ACTIVE.set(active)
        record = StageRecord(
            name=name,
            status="success",
            started_at=_now(),
            finished_at=_now(),
            duration_ms=max(0.0, float(duration_ms or 0.0)),
            input_summary=inspect_value(input_data, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier),
            output_summary=inspect_value(output_data, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier),
        )
        self._analyze_record(record, active)
        self._apply_live_checks(record, input_data, output_data)
        self._finalize_stage_status(record)
        active.run.stages.append(record)
        if owns:
            self._finish_context(active)
            if token is not None:
                _ACTIVE.reset(token)
        return record

    def add_check(
        self,
        stage: str | None,
        check: Callable[[Any], Any],
        *,
        message: str,
        severity: str = "warning",
        target: str = "output",
        code: str = "custom_check_failed",
    ) -> None:
        """Register a custom predicate; False or a message string creates a finding."""
        if severity not in {"info", "warning", "error"}:
            raise ValueError("severity must be info, warning, or error")
        if target not in {"input", "output"}:
            raise ValueError("target must be input or output")
        if not callable(check):
            raise TypeError("check must be callable")
        self._checks.append(_Check(stage, check, message, severity, target, code))

    def expect_range(
        self,
        stage: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        target: str = "output",
        severity: str = "warning",
    ) -> None:
        """Require all inspectable numeric values to fit within an inclusive range."""
        if minimum is None and maximum is None:
            raise ValueError("At least one of minimum or maximum is required")

        def check(value: Any) -> bool:
            summary = inspect_value(value, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier)
            low, high = summary.get("minimum"), summary.get("maximum")
            if low is None or high is None:
                return False
            return (minimum is None or low >= minimum) and (maximum is None or high <= maximum)

        bound = f"{minimum if minimum is not None else '-infinity'} to {maximum if maximum is not None else 'infinity'}"
        self.add_check(
            stage, check, message=f"Numeric values must be within {bound}", severity=severity,
            target=target, code="numeric_range_violation",
        )

    def expect_shape(
        self,
        stage: str,
        shape: Sequence[int | None],
        *,
        target: str = "output",
        severity: str = "warning",
    ) -> None:
        """Require a shape while allowing ``None`` dimensions to vary.

        Example: ``pipeline.expect_shape('infer', (None, 16))`` accepts batch
        sizes of any value while requiring 16 features in the second dimension.
        Matching wildcard contracts also suppress expected cross-run shape/size
        warnings for that stage and target.
        """
        if target not in {"input", "output"}:
            raise ValueError("target must be input or output")
        expected: tuple[int | None, ...] = tuple(shape)
        if not expected or any(item is not None and (not isinstance(item, int) or item < 0) for item in expected):
            raise ValueError("shape must contain non-negative integers or None")
        self._shape_contracts[(stage, target)] = expected

        def check(value: Any) -> bool:
            actual = inspect_value(value, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier).get("shape")
            return _shape_matches(actual, expected)

        rendered = "(" + ", ".join("*" if item is None else str(item) for item in expected) + ")"
        self.add_check(
            stage, check, message=f"Expected shape {rendered}", severity=severity,
            target=target, code="shape_contract_violation",
        )

    def expect_outlier_rate(
        self,
        stage: str,
        *,
        maximum_ratio: float,
        target: str = "output",
        severity: str = "warning",
    ) -> None:
        """Require the IQR outlier ratio to stay at or below a configured value."""
        if not 0 <= maximum_ratio <= 1:
            raise ValueError("maximum_ratio must be between 0 and 1")

        def check(value: Any) -> bool:
            summary = inspect_value(value, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier)
            ratio = summary.get("outlier_ratio")
            numeric_count = int(summary.get("numeric_count", 0) or 0)
            # A contract cannot be considered satisfied when its input contains
            # no measurable numeric values. Fail visibly instead of silently
            # treating missing statistics as a zero-outlier result.
            return numeric_count > 0 and ratio is not None and ratio <= maximum_ratio

        self.add_check(
            stage, check, message=f"Outlier ratio must be <= {maximum_ratio:.2%}",
            severity=severity, target=target, code="outlier_rate_violation",
        )

    def run(self, data: Any, *, metadata: dict[str, Any] | None = None) -> Any:
        """Run registered stages sequentially, passing each output to the next."""
        if not self._stages:
            raise RuntimeError("No stages registered. Add a stage with @stage(pipeline) first.")
        context = self._new_context(metadata=metadata)
        token = _ACTIVE.set(context)
        value = data
        try:
            for _, tracked in self._stages:
                value = tracked(value)
            return value
        except BaseException:
            context.run.status = "failed"
            raise
        finally:
            self._finish_context(context)
            _ACTIVE.reset(token)

    def _new_context(self, metadata: dict[str, Any] | None = None) -> _RunContext:
        if self._store:
            baseline_runs = self._store.list(self.name, self.performance_window)
        else:
            baseline_runs = list(reversed(self._memory_history[-self.performance_window:]))
        run = RunRecord(
            run_id=uuid.uuid4().hex[:12], pipeline_name=self.name, status="running",
            started_at=_now(), finished_at="", duration_ms=0.0, metadata=dict(metadata or {}),
        )
        return _RunContext(self, run, time.perf_counter(), baseline_runs)

    def _finish_context(self, context: _RunContext) -> None:
        context.run.finished_at = _now()
        context.run.duration_ms = (time.perf_counter() - context.started_perf) * 1000
        if context.run.status == "running":
            if any(stage.status == "failed" for stage in context.run.stages):
                context.run.status = "failed"
            elif any(f.severity in {"warning", "error"} for stage in context.run.stages for f in stage.findings):
                context.run.status = "warning"
            else:
                context.run.status = "success"
        self._last_run = context.run
        if self._store:
            self._store.save(context.run)
        else:
            self._memory_history.append(context.run)
            if len(self._memory_history) > self.max_history:
                del self._memory_history[:-self.max_history]

    def _run_single_stage(self, name: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        context = self._new_context()
        token = _ACTIVE.set(context)
        try:
            return self._execute_stage(name, function, *args, **kwargs)
        except BaseException:
            context.run.status = "failed"
            raise
        finally:
            self._finish_context(context)
            _ACTIVE.reset(token)

    def _execute_stage(self, name: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        context = _ACTIVE.get()
        if context is None or context.pipeline is not self:
            raise RuntimeError("Internal StageWatch execution context is missing")
        input_data = args[0] if args else kwargs
        input_summary = inspect_value(input_data, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier)
        started_at = _now()
        started = time.perf_counter()
        try:
            output_data = function(*args, **kwargs)
        except BaseException as exc:
            record = StageRecord(
                name=name, status="failed", started_at=started_at, finished_at=_now(),
                duration_ms=(time.perf_counter() - started) * 1000,
                input_summary=input_summary, output_summary={},
                error_type=type(exc).__name__, error_message=str(exc)[:1000],
            )
            self._analyze_record(record, context)
            self._apply_live_checks(record, input_data, None)
            self._finalize_stage_status(record)
            record.status = "failed"
            context.run.stages.append(record)
            raise
        record = StageRecord(
            name=name, status="success", started_at=started_at, finished_at=_now(),
            duration_ms=(time.perf_counter() - started) * 1000,
            input_summary=input_summary,
            output_summary=inspect_value(output_data, deep_scan_limit_bytes=self.deep_scan_limit_bytes, inspect_gpu=self.inspect_gpu, outlier_iqr_multiplier=self.outlier_iqr_multiplier),
        )
        self._analyze_record(record, context)
        self._apply_live_checks(record, input_data, output_data)
        self._finalize_stage_status(record)
        context.run.stages.append(record)
        return output_data

    def _contract(self, stage_name: str, target: str) -> tuple[int | None, ...] | None:
        return self._shape_contracts.get((stage_name, target))

    def _add_value_findings(
        self, record: StageRecord, label: str, summary: dict[str, Any], context: _RunContext,
    ) -> None:
        if not summary:
            return
        candidates: list[tuple[str, str, int]] = []
        for key, code, message in (
            ("nan_count", "nan_detected", "NaN values detected"),
            ("inf_count", "infinity_detected", "Infinite values detected"),
            ("missing_count", "missing_values_detected", "Missing values detected"),
            ("none_count", "none_values_detected", "None values detected"),
        ):
            count = int(summary.get(key, 0) or 0)
            if count:
                candidates.append((code, message, count))
        if summary.get("empty"):
            candidates.append(("empty_value", f"Empty {label} detected", 1))
        outlier_count = int(summary.get("outlier_count", 0) or 0)
        outlier_ratio = float(summary.get("outlier_ratio", 0.0) or 0.0)
        if (
            self.detect_outliers
            and outlier_count >= self.outlier_min_count
            and outlier_ratio >= self.outlier_min_ratio
        ):
            candidates.append((
                "statistical_outliers_detected",
                f"Potential statistical outliers detected: {outlier_count} ({outlier_ratio:.2%})",
                outlier_count,
            ))

        active_codes = {code for code, _, _ in candidates}
        # Clear a previously observed anomaly when it is absent at this stage
        # input. The output pass below can then report a newly introduced issue.
        if label == "input":
            for code in list(context.active_anomalies):
                if code not in active_codes:
                    context.active_anomalies.pop(code, None)
        else:
            # Empty output is handled by the candidate set; absent values clear
            # the active count so later stages can report newly introduced data.
            for code in list(context.active_anomalies):
                if code not in active_codes:
                    context.active_anomalies.pop(code, None)

        for code, message, count in candidates:
            previous_count = context.active_anomalies.get(code)
            if previous_count == count:
                continue
            context.active_anomalies[code] = count
            details: dict[str, Any] = {"count": count}
            if code == "statistical_outliers_detected":
                field_map = summary.get("numeric_columns") or summary.get("numeric_fields") or {}
                field_details = [
                    {
                        "field": field_name,
                        "count": int(metrics.get("outlier_count", 0) or 0),
                        "ratio": float(metrics.get("outlier_ratio", 0.0) or 0.0),
                        "lower_fence": metrics.get("outlier_lower_fence"),
                        "upper_fence": metrics.get("outlier_upper_fence"),
                    }
                    for field_name, metrics in field_map.items()
                    if int(metrics.get("outlier_count", 0) or 0) > 0
                ]
                details.update({
                    "ratio": outlier_ratio,
                    "iqr": summary.get("iqr"),
                    "lower_fence": summary.get("outlier_lower_fence"),
                    "upper_fence": summary.get("outlier_upper_fence"),
                    "fields": field_details,
                    "method": "Tukey IQR",
                    "multiplier": self.outlier_iqr_multiplier,
                })
            record.findings.append(Finding(code, message, "warning", label, details))

    def _performance_baseline(self, stage_name: str, context: _RunContext) -> list[float]:
        durations: list[float] = []
        for run in context.baseline_runs:
            previous_stage = next((stage for stage in run.stages if stage.name == stage_name), None)
            if previous_stage and previous_stage.status != "failed":
                durations.append(previous_stage.duration_ms)
        return durations

    def _detect_performance_regression(self, record: StageRecord, context: _RunContext) -> None:
        if self.slowdown_threshold is None:
            return
        durations = self._performance_baseline(record.name, context)
        durations = [duration for duration in durations if duration >= self.performance_min_duration_ms]
        if len(durations) < self.performance_min_samples:
            return
        baseline = statistics.median(durations)
        if baseline <= 0 or record.duration_ms < self.performance_min_duration_ms:
            return
        slowdown = (record.duration_ms - baseline) / baseline
        if slowdown >= self.slowdown_threshold:
            record.findings.append(Finding(
                "performance_regression",
                f"Stage is {slowdown:.0%} slower than its baseline median",
                "warning", "performance",
                {
                    "baseline_median_ms": baseline,
                    "current_ms": record.duration_ms,
                    "slowdown_pct": slowdown * 100,
                    "sample_count": len(durations),
                    "baseline_method": "median of recent successful runs",
                },
            ))

    def _detect_distribution_shift(self, record: StageRecord, context: _RunContext) -> None:
        threshold = self.distribution_shift_threshold
        if threshold is None:
            return
        current = record.output_summary
        baseline_summaries: list[dict[str, Any]] = []
        for run in context.baseline_runs:
            prior_stage = next((stage for stage in run.stages if stage.name == record.name), None)
            summary = prior_stage.output_summary if prior_stage and prior_stage.status != "failed" else {}
            if summary:
                baseline_summaries.append(summary)
        if len(baseline_summaries) < self.distribution_min_samples:
            return

        column_map = current.get("numeric_columns") or current.get("numeric_fields")
        changed_columns: list[dict[str, Any]] = []
        if isinstance(column_map, dict) and column_map:
            for column_name, metrics in column_map.items():
                means: list[float] = []
                scales: list[float] = []
                for summary in baseline_summaries:
                    baseline_column = (summary.get("numeric_columns") or {}).get(column_name)
                    if isinstance(baseline_column, dict) and baseline_column.get("mean") is not None and baseline_column.get("std") is not None:
                        means.append(float(baseline_column["mean"]))
                        scales.append(float(baseline_column["std"]))
                if len(means) < self.distribution_min_samples or metrics.get("mean") is None or metrics.get("std") is None:
                    continue
                baseline_mean = statistics.median(means)
                baseline_std = statistics.median(scales)
                floor = max(abs(baseline_mean) * 1e-6, 1e-9)
                scale = max(baseline_std, floor)
                mean_shift = abs(float(metrics["mean"]) - baseline_mean) / scale
                current_std = float(metrics["std"])
                spread_ratio = max(current_std, baseline_std, floor) / max(min(current_std, baseline_std), floor)
                if mean_shift >= threshold or spread_ratio >= threshold:
                    changed_columns.append({
                        "column": column_name,
                        "baseline_mean": baseline_mean,
                        "current_mean": float(metrics["mean"]),
                        "mean_shift_in_baseline_std": mean_shift,
                        "baseline_std": baseline_std,
                        "current_std": current_std,
                        "spread_ratio": spread_ratio,
                        "sample_count": len(means),
                    })
        else:
            if "numeric_fields" in current or current.get("mean") is None or current.get("std") is None:
                return
            means = [float(summary["mean"]) for summary in baseline_summaries if summary.get("mean") is not None and summary.get("std") is not None]
            scales = [float(summary["std"]) for summary in baseline_summaries if summary.get("mean") is not None and summary.get("std") is not None]
            if len(means) < self.distribution_min_samples:
                return
            baseline_mean = statistics.median(means)
            baseline_std = statistics.median(scales)
            floor = max(abs(baseline_mean) * 1e-6, 1e-9)
            scale = max(baseline_std, floor)
            mean_shift = abs(float(current["mean"]) - baseline_mean) / scale
            current_std = float(current["std"])
            spread_ratio = max(current_std, baseline_std, floor) / max(min(current_std, baseline_std), floor)
            if mean_shift >= threshold or spread_ratio >= threshold:
                changed_columns.append({
                    "column": None,
                    "baseline_mean": baseline_mean,
                    "current_mean": float(current["mean"]),
                    "mean_shift_in_baseline_std": mean_shift,
                    "baseline_std": baseline_std,
                    "current_std": current_std,
                    "spread_ratio": spread_ratio,
                    "sample_count": len(means),
                })
        if changed_columns:
            record.findings.append(Finding(
                "distribution_shift",
                "Numeric output distribution differs materially from recent runs",
                "warning", "output", {
                    "columns": changed_columns,
                    "threshold": threshold,
                    "method": "median baseline; mean shift in baseline standard deviations and spread ratio",
                },
            ))

    def _analyze_record(self, record: StageRecord, context: _RunContext) -> None:
        input_summary = record.input_summary
        output_summary = record.output_summary
        self._add_value_findings(record, "input", input_summary, context)
        self._add_value_findings(record, "output", output_summary, context)
        self._detect_performance_regression(record, context)
        self._detect_distribution_shift(record, context)

        previous = context.previous
        previous_stage = next((item for item in previous.stages if item.name == record.name), None) if previous else None
        if previous_stage is None:
            return

        input_changes = _changed_fields(previous_stage.input_summary, input_summary)
        output_changes = _changed_fields(previous_stage.output_summary, output_summary)
        input_contract = self._contract(record.name, "input")
        input_shape_dynamic = _shape_contract_allows_change(
            previous_stage.input_summary, input_summary, input_contract
        )
        if input_shape_dynamic:
            input_changes = [field for field in input_changes if field not in {"shape", "length"}]
            context.accepted_dynamic_source = context.accepted_dynamic_source or record.name
            context.run.insights.append({
                "kind": "dynamic_input_dimension_accepted",
                "stage": record.name,
                "previous_shape": previous_stage.input_summary.get("shape"),
                "current_shape": input_summary.get("shape"),
                "contract": ["*" if item is None else item for item in input_contract or ()],
            })
        old_size = previous_stage.output_summary.get("estimated_size_bytes")
        new_size = output_summary.get("estimated_size_bytes")
        size_change = None
        if old_size and new_size is not None:
            size_change = abs(float(new_size) - float(old_size)) / float(old_size)

        output_contract = self._contract(record.name, "output")
        shape_dynamic = _shape_contract_allows_change(previous_stage.output_summary, output_summary, output_contract)
        if shape_dynamic:
            output_changes = [field for field in output_changes if field not in {"shape", "length"}]
            size_change = None
            context.accepted_dynamic_source = context.accepted_dynamic_source or record.name
            context.run.insights.append({
                "kind": "dynamic_dimension_accepted",
                "stage": record.name,
                "previous_shape": previous_stage.output_summary.get("shape"),
                "current_shape": output_summary.get("shape"),
                "contract": ["*" if item is None else item for item in output_contract or ()],
            })

        # A wildcard output contract on the immediately preceding stage also
        # governs the shape it passes into this stage. This prevents a permitted
        # batch-size change from becoming a cascade of false schema warnings.
        upstream_dynamic = False
        if context.run.stages and previous is not None:
            current_predecessor = context.run.stages[-1]
            old_predecessor = next((item for item in previous.stages if item.name == current_predecessor.name), None)
            predecessor_contract = self._contract(current_predecessor.name, "output")
            if old_predecessor and _shape_contract_allows_change(
                old_predecessor.output_summary, current_predecessor.output_summary, predecessor_contract
            ):
                current_input_shape = input_summary.get("shape")
                predecessor_shape = current_predecessor.output_summary.get("shape")
                if current_input_shape == predecessor_shape:
                    input_changes = [field for field in input_changes if field not in {"shape", "length"}]
                    upstream_dynamic = True
                    if output_changes and all(field in {"shape", "length"} for field in output_changes):
                        output_changes = []
                        size_change = None
                    context.run.insights.append({
                        "kind": "dynamic_dimension_propagated",
                        "stage": record.name,
                        "source_stage": current_predecessor.name,
                    })

        # Continue an already accepted dynamic dimension through sequential
        # transforms when only shape/length footprints change downstream.
        if context.accepted_dynamic_source and not context.root_cause_stage:
            input_structural = set(input_changes) - {"shape", "length"}
            output_structural = set(output_changes) - {"shape", "length"}
            if not input_structural and not output_structural and (input_changes or output_changes or size_change is not None):
                upstream_dynamic = True
                input_changes = []
                output_changes = []
                size_change = None
                context.run.insights.append({
                    "kind": "dynamic_dimension_propagated",
                    "stage": record.name,
                    "source_stage": context.accepted_dynamic_source,
                })

        if upstream_dynamic and not input_changes and not output_changes and size_change is None:
            return

        size_changed = (
            self.size_change_threshold is not None
            and size_change is not None
            and size_change >= self.size_change_threshold
        )

        if context.root_cause_stage and self.aggregate_upstream_changes:
            # Do not hide an independent downstream output contract change just
            # because an earlier stage also changed. Shape/length/footprint-only
            # deltas are treated as likely propagation; type/dtype/key changes
            # remain visible as local warnings.
            independent_fields = [field for field in output_changes if field not in {"shape", "length"}]
            local_change = bool(independent_fields) or (not input_changes and bool(output_changes))
            if local_change:
                record.findings.append(Finding(
                    "schema_changed",
                    "This stage also has an output schema change beyond the observed upstream impact",
                    "warning", "output", {
                        "root_stage": record.name,
                        "upstream_root_stage": context.root_cause_stage,
                        "changed_fields": independent_fields or output_changes,
                        "previous": {key: previous_stage.output_summary.get(key) for key in (independent_fields or output_changes)},
                        "current": {key: output_summary.get(key) for key in (independent_fields or output_changes)},
                    },
                ))
            propagated_fields = sorted(set(
                input_changes + [field for field in output_changes if field in {"shape", "length"}]
                + (["estimated_size_bytes"] if size_changed else [])
            ))
            if propagated_fields:
                record.findings.append(Finding(
                    "upstream_change_propagated",
                    f"Changes in this stage are likely propagated from {context.root_cause_stage}",
                    "info", "output", {
                        "root_stage": context.root_cause_stage,
                        "root_cause": context.root_cause_message,
                        "affected_fields": propagated_fields,
                        "interpretation": "downstream impact; inspect the root stage first",
                    },
                ))
                context.run.insights.append({
                    "kind": "upstream_impact",
                    "stage": record.name,
                    "root_stage": context.root_cause_stage,
                    "affected_fields": propagated_fields,
                })
            return

        if context.root_cause_stage is None and input_changes:
            if not context.run.stages:
                root_stage = f"pipeline input -> {record.name}"
                message = "The input structure changed before the first monitored stage"
            else:
                root_stage = f"input to {record.name}"
                message = "The input structure changed at this stage; the upstream source is outside the observed boundary"
            context.root_cause_stage = root_stage
            context.root_cause_message = message
            record.findings.append(Finding(
                "pipeline_input_changed",
                message,
                "warning", "input", {
                    "root_stage": root_stage,
                    "changed_fields": input_changes,
                    "previous": {key: previous_stage.input_summary.get(key) for key in input_changes},
                    "current": {key: input_summary.get(key) for key in input_changes},
                    "stage_output_also_changed": bool(output_changes or size_changed),
                },
            ))
            context.run.insights.append({"kind": "root_cause", "stage": root_stage, "message": message})
            return

        if output_changes:
            context.root_cause_stage = record.name
            context.root_cause_message = "The stage output schema differs while its input schema remained stable"
            record.findings.append(Finding(
                "schema_changed",
                "Stage output schema changed since the previous run",
                "warning", "output", {
                    "root_stage": record.name,
                    "changed_fields": output_changes,
                    "previous": {key: previous_stage.output_summary.get(key) for key in output_changes},
                    "current": {key: output_summary.get(key) for key in output_changes},
                    "size_change_pct": size_change * 100 if size_change is not None else None,
                },
            ))
            context.run.insights.append({
                "kind": "root_cause", "stage": record.name,
                "message": context.root_cause_message,
            })
            return

        if size_changed:
            context.root_cause_stage = record.name
            context.root_cause_message = "The output footprint changed while the inspected schema remained stable"
            record.findings.append(Finding(
                "data_size_changed",
                f"Output data size changed by {size_change:.0%}",
                "warning", "output", {
                    "root_stage": record.name,
                    "previous_bytes": old_size,
                    "current_bytes": new_size,
                    "change_pct": size_change * 100,
                },
            ))
            context.run.insights.append({
                "kind": "root_cause", "stage": record.name,
                "message": context.root_cause_message,
            })

    def _apply_live_checks(self, record: StageRecord, input_data: Any, output_data: Any) -> None:
        for check in self._checks:
            if check.stage is not None and check.stage != record.name:
                continue
            value = input_data if check.target == "input" else output_data
            try:
                result = check.function(value)
                if result is False or isinstance(result, str):
                    message = result if isinstance(result, str) else check.message
                    record.findings.append(Finding(check.code, str(message), check.severity, check.target))
            except Exception as exc:
                record.findings.append(Finding(
                    "validator_error", f"Custom validator failed: {type(exc).__name__}: {exc}",
                    "error", check.target,
                ))

    @staticmethod
    def _finalize_stage_status(record: StageRecord) -> None:
        if record.status == "failed":
            return
        if any(finding.severity in {"warning", "error"} for finding in record.findings):
            record.status = "warning"
        else:
            record.status = "success"

    def history(self, limit: int = 20) -> list[RunRecord]:
        if self._store:
            return self._store.list(self.name, limit)
        return list(reversed(self._memory_history[-max(1, int(limit)):]))

    def get_run(self, run_id: str) -> RunRecord | None:
        if self._last_run and self._last_run.run_id == run_id:
            return self._last_run
        if self._store:
            return self._store.get(run_id)
        return next((run for run in self._memory_history if run.run_id == run_id), None)

    def compare(self, run_a: str | None = None, run_b: str | None = None) -> Comparison:
        runs = self.history(limit=1000)
        if run_a is None or run_b is None:
            if len(runs) < 2:
                raise ValueError("At least two recorded runs are required for comparison")
            a, b = runs[1], runs[0]
        else:
            a, b = self.get_run(run_a), self.get_run(run_b)
            if a is None or b is None:
                raise KeyError("One or both run IDs were not found in local history")
        stage_changes: list[dict[str, Any]] = []
        performance_regressions: list[dict[str, Any]] = []
        amap, bmap = {item.name: item for item in a.stages}, {item.name: item for item in b.stages}
        for name in list(dict.fromkeys(list(amap) + list(bmap))):
            old, new = amap.get(name), bmap.get(name)
            if old is None:
                stage_changes.append({"stage": name, "change": "added"})
                continue
            if new is None:
                stage_changes.append({"stage": name, "change": "removed"})
                continue
            parts = []
            if old.status != new.status:
                parts.append(f"status {old.status} -> {new.status}")
            contract = self._contract(name, "output")
            if old.output_summary.get("shape") != new.output_summary.get("shape") and not _shape_contract_allows_change(old.output_summary, new.output_summary, contract):
                parts.append("output shape changed")
            if old.output_summary.get("type") != new.output_summary.get("type"):
                parts.append("output type changed")
            if old.output_summary.get("dtype") != new.output_summary.get("dtype"):
                parts.append("output dtype changed")
            old_size = old.output_summary.get("estimated_size_bytes")
            new_size = new.output_summary.get("estimated_size_bytes")
            if old_size != new_size and not _shape_contract_allows_change(old.output_summary, new.output_summary, contract):
                parts.append("output size changed")
            delta_ms = new.duration_ms - old.duration_ms
            if (
                min(old.duration_ms, new.duration_ms) >= self.performance_min_duration_ms
                and old.duration_ms > 0
                and delta_ms / old.duration_ms >= self.performance_comparison_threshold
            ):
                parts.append(f"duration increased {old.duration_ms:.2f} -> {new.duration_ms:.2f} ms")
            if len(new.findings) != len(old.findings):
                parts.append(f"finding count {len(old.findings)} -> {len(new.findings)}")
            if parts:
                stage_changes.append({"stage": name, "change": "; ".join(parts)})
            for finding in new.findings:
                if finding.code == "performance_regression":
                    performance_regressions.append({
                        "stage": name,
                        "slowdown_pct": float(finding.details.get("slowdown_pct", 0.0)),
                        "baseline_median_ms": finding.details.get("baseline_median_ms"),
                    })
        duration_pct = ((b.duration_ms - a.duration_ms) / a.duration_ms * 100) if a.duration_ms else 0.0
        return Comparison(a.run_id, b.run_id, stage_changes, {
            "duration_a_ms": a.duration_ms,
            "duration_b_ms": b.duration_ms,
            "duration_change_pct": duration_pct,
            "status_a": a.status,
            "status_b": b.status,
            "performance_regressions": performance_regressions,
        })

    def report(self, format: str = "terminal", *, run_id: str | None = None, path: str | Path | None = None) -> str | Path:
        """Render a run as terminal, JSON or standalone HTML."""
        selected = self.get_run(run_id) if run_id else (self._last_run or (self._store.latest(self.name) if self._store else None))
        if selected is None:
            raise ValueError("No recorded run is available to report")
        from .reporters import render_html, render_json, render_terminal
        if format == "terminal":
            content = render_terminal(selected)
        elif format == "json":
            content = render_json(selected)
        elif format == "html":
            content = render_html(selected, self.history(limit=20))
            target = Path(path) if path else Path(f"{_slug(self.name)}-report.html")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return target
        else:
            raise ValueError("format must be terminal, json or html")
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return target
        return content

    def clear_history(self) -> int:
        if self._store:
            return self._store.delete_all(self.name)
        count = len(self._memory_history)
        self._memory_history.clear()
        self._last_run = None
        return count


def stage(pipeline: Pipeline, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator shortcut: ``@stage(pipeline)`` or ``@stage(pipeline, 'load')``."""
    if not isinstance(pipeline, Pipeline):
        raise TypeError("stage() expects a Pipeline instance")
    return pipeline.stage_decorator(name)
