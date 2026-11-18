from __future__ import annotations

import html
from ..models import RunRecord


def render_html(run: RunRecord, history: list[RunRecord] | None = None) -> str:
    history = history or []
    findings = sum(len(stage.findings) for stage in run.stages)
    warnings = sum(f.severity in {"warning", "error"} for stage in run.stages for f in stage.findings)
    stage_rows = []
    for stage in run.stages:
        status_class = "failed" if stage.status == "failed" else ("warning" if stage.status == "warning" else "success")
        details = "".join(
            f'<li><span class="sev {html.escape(f.severity)}">{html.escape(f.severity.upper())}</span> '
            f'<code>{html.escape(f.code)}</code> — {html.escape(f.message)} '
            f'<small>({html.escape(f.location)})</small>'
            f'{("<small> Root: " + html.escape(str(f.details.get("root_stage"))) + "</small>") if f.details.get("root_stage") else ""}</li>'
            for f in stage.findings
        )
        error = f'<p class="error">{html.escape(stage.error_type or "Error")}: {html.escape(stage.error_message or "")}</p>' if stage.error_type else ""
        stage_rows.append(
            f'<tr><td><strong>{html.escape(stage.name)}</strong>{error}{("<ul>" + details + "</ul>") if details else ""}</td>'
            f'<td><span class="status {status_class}">{html.escape(stage.status.upper())}</span></td>'
            f'<td class="num">{stage.duration_ms:.2f} ms</td>'
            f'<td class="num">{int(stage.output_summary.get("estimated_size_bytes", 0) or 0):,} B</td></tr>'
        )
    history_items = "".join(
        f'<tr><td><code>{html.escape(item.run_id)}</code></td><td>{html.escape(item.started_at)}</td>'
        f'<td>{html.escape(item.status.upper())}</td><td class="num">{item.duration_ms:.2f} ms</td></tr>'
        for item in history[:20]
    ) or '<tr><td colspan="4">No previous runs recorded.</td></tr>'
    insight_items = "".join(
        '<li><strong>' + html.escape(str(item.get("kind", "insight")).replace("_", " ").title()) + '</strong> — '
        + html.escape(str(item.get("message") or item.get("stage") or "Pipeline observation"))
        + (" <small>(stage: " + html.escape(str(item.get("stage"))) + ")</small>" if item.get("stage") else "")
        + (" <small>(root: " + html.escape(str(item.get("root_stage") or item.get("source_stage"))) + ")</small>" if item.get("root_stage") or item.get("source_stage") else "")
        + "</li>"
        for item in run.insights
    ) or "<li>No additional pipeline insights for this run.</li>"
    status_class = "failed" if run.status == "failed" else ("warning" if run.status == "warning" else "success")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StageWatch — {html.escape(run.pipeline_name)}</title>
<style>
:root{{--bg:#0b1220;--panel:#121d2e;--line:#24334a;--text:#e7edf6;--muted:#9aabc1;--accent:#62d6c5;--red:#ff7777;--yellow:#f6c96b;--green:#71d6a3}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:48px auto;padding:0 22px}}header{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:28px}}h1{{font-size:30px;margin:0}}h2{{font-size:18px;margin:0 0 16px}}p{{color:var(--muted)}}.eyebrow{{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}}.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}}.metric{{font-size:25px;font-weight:750}}.label{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
.status,.sev{{display:inline-block;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:800;letter-spacing:.05em}}.success{{color:var(--green);background:#17382e}}.warning{{color:var(--yellow);background:#3b321c}}.failed,.error{{color:var(--red);background:#40252b}}.info{{color:#83c9ef;background:#173047}}table{{border-collapse:collapse;width:100%}}th,td{{padding:13px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}td{{font-size:13px}}.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}code{{color:var(--accent);font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}ul{{margin:8px 0 2px;padding-left:18px;color:var(--muted)}}li{{margin:5px 0}}small{{color:var(--muted)}}.error{{padding:8px;border-radius:7px;margin:8px 0;font-size:12px}}.meta{{color:var(--muted);font-size:13px}}.panel{{margin:18px 0;overflow-x:auto}}footer{{color:var(--muted);font-size:12px;margin:24px 0}}@media(max-width:760px){{.grid{{grid-template-columns:repeat(2,1fr)}}header{{display:block}}main{{margin:25px auto}}}}
</style></head><body><main>
<header><div><div class="eyebrow">Local pipeline observability</div><h1>{html.escape(run.pipeline_name)}</h1><p class="meta">Run <code>{html.escape(run.run_id)}</code> · {html.escape(run.started_at)}</p></div>
<div class="status {status_class}">{html.escape(run.status.upper())}</div></header>
<section class="grid"><div class="card"><div class="label">Total duration</div><div class="metric">{run.duration_ms:.2f} ms</div></div>
<div class="card"><div class="label">Stages</div><div class="metric">{len(run.stages)}</div></div>
<div class="card"><div class="label">Findings</div><div class="metric">{findings}</div></div>
<div class="card"><div class="label">Warnings / errors</div><div class="metric">{warnings}</div></div></section>
<section class="panel"><h2>Root-cause and pipeline insights</h2><ul>{insight_items}</ul></section>
<section class="panel"><h2>Stage execution</h2><table><thead><tr><th>Stage / findings</th><th>Status</th><th class="num">Duration</th><th class="num">Output footprint</th></tr></thead><tbody>{''.join(stage_rows) or '<tr><td colspan="4">No stages recorded.</td></tr>'}</tbody></table></section>
<section class="panel"><h2>Recent execution history</h2><table><thead><tr><th>Run ID</th><th>Started</th><th>Status</th><th class="num">Duration</th></tr></thead><tbody>{history_items}</tbody></table></section>
<footer>Generated locally by StageWatch. Raw pipeline inputs and outputs are not included in this report.</footer>
</main></body></html>'''
