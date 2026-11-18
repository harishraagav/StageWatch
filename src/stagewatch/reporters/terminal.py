from __future__ import annotations

from ..models import RunRecord


def render_terminal(run: RunRecord) -> str:
    width = 84
    lines = ["=" * width, f" STAGEWATCH  |  {run.pipeline_name}", "=" * width]
    lines.extend([
        f"Run ID:       {run.run_id}",
        f"Status:       {run.status.upper()}",
        f"Started:      {run.started_at}",
        f"Duration:     {run.duration_ms:.2f} ms",
        f"Stages:       {len(run.stages)}",
        "-" * width,
        f"{'STAGE':<28} {'STATUS':<10} {'DURATION':>12} {'FINDINGS':>10}",
        "-" * width,
    ])
    for item in run.stages:
        lines.append(f"{item.name[:27]:<28} {item.status:<10} {item.duration_ms:>9.2f} ms {len(item.findings):>10}")
        for finding in item.findings:
            lines.append(f"  [{finding.severity.upper()}] {finding.code}: {finding.message}")
            root = finding.details.get("root_stage")
            if root:
                lines.append(f"      root/related stage: {root}")
        if item.error_type:
            lines.append(f"  [ERROR] {item.error_type}: {item.error_message or ''}")
    if run.insights:
        lines.extend(["-" * width, "PIPELINE INSIGHTS"])
        for insight in run.insights:
            kind = insight.get("kind", "insight")
            stage = insight.get("stage", "pipeline")
            root = insight.get("root_stage") or insight.get("source_stage")
            detail = insight.get("message") or ", ".join(insight.get("affected_fields", []))
            suffix = f" (source: {root})" if root else ""
            lines.append(f"  [{kind}] {stage}: {detail}{suffix}")
    lines.extend(["-" * width, f"Total findings: {sum(len(s.findings) for s in run.stages)}", "=" * width])
    return "\n".join(lines)
