"""Serializable data models used by StageWatch."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _clean(value: Any) -> Any:
    """Convert values to JSON-safe primitives without retaining arbitrary objects."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


@dataclass(slots=True)
class Finding:
    code: str
    message: str
    severity: str = "warning"
    location: str = "output"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class StageRecord:
    name: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["findings"] = [finding.to_dict() for finding in self.findings]
        return _clean(result)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageRecord":
        values = dict(data)
        values["findings"] = [Finding(**finding) for finding in values.get("findings", [])]
        return cls(**values)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    pipeline_name: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    stages: list[StageRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    insights: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "stages": [stage.to_dict() for stage in self.stages],
            "metadata": self.metadata,
            "insights": self.insights,
        })

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        """Load current and pre-0.2.0 records (which do not contain insights)."""
        values = dict(data)
        values["stages"] = [StageRecord.from_dict(stage) for stage in values.get("stages", [])]
        values.setdefault("insights", [])
        return cls(**values)


@dataclass(slots=True)
class Comparison:
    run_a: str
    run_b: str
    stage_changes: list[dict[str, Any]]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def explain(self) -> str:
        lines = [f"StageWatch comparison: {self.run_a} -> {self.run_b}"]
        lines.append(
            f"Duration: {self.summary.get('duration_a_ms', 0):.2f} ms -> "
            f"{self.summary.get('duration_b_ms', 0):.2f} ms"
        )
        lines.append(f"Duration change: {self.summary.get('duration_change_pct', 0):+.1f}%")
        if not self.stage_changes:
            lines.append("No material stage-level changes detected.")
        for item in self.stage_changes:
            lines.append(f"- {item['stage']}: {item['change']}")
        regressions = self.summary.get("performance_regressions", [])
        for item in regressions:
            lines.append(
                f"  performance regression: {item['stage']} is {item['slowdown_pct']:.1f}% slower "
                f"than baseline median"
            )
        return "\n".join(lines)
