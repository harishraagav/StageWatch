"""Command line interface for local StageWatch history databases."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .history import HistoryStore
from .reporters import render_html, render_json, render_terminal


def _default_db(value: str | None) -> Path:
    if value:
        return Path(value)
    folder = Path(".stagewatch")
    databases = sorted(folder.glob("*.sqlite3")) if folder.exists() else []
    if len(databases) == 1:
        return databases[0]
    if not databases:
        raise FileNotFoundError("No StageWatch database found. Pass --db PATH or run an instrumented pipeline first.")
    raise RuntimeError("Multiple StageWatch databases found. Specify one with --db PATH.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stagewatch", description="Inspect local Python pipeline execution history.")
    parser.add_argument("--version", action="version", version=f"StageWatch {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="Render a recorded pipeline run")
    report.add_argument("--db", help="SQLite history database path")
    report.add_argument("--run-id", help="Run ID (defaults to latest)")
    report.add_argument("--format", choices=("terminal", "json", "html"), default="terminal")
    report.add_argument("--output", help="Write report to this path")
    report.add_argument("--pipeline", help="Filter by pipeline name")
    history = sub.add_parser("history", help="List recorded runs")
    history.add_argument("--db", help="SQLite history database path")
    history.add_argument("--pipeline", help="Filter by pipeline name")
    history.add_argument("--limit", type=int, default=20)
    compare = sub.add_parser("compare", help="Compare two recorded runs")
    compare.add_argument("run_a")
    compare.add_argument("run_b")
    compare.add_argument("--db", help="SQLite history database path")
    compare.add_argument("--pipeline", help="Filter by pipeline name")
    return parser


def main(argv: list[str] | None = None) -> int:
    # On Windows, the active console code page may not encode all Unicode data
    # (for example, user-defined stage names). Escape unsupported characters
    # rather than letting a report crash with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        db = _default_db(args.db)
        store = HistoryStore(db)
        if args.command == "history":
            runs = store.list(args.pipeline, args.limit)
            if not runs:
                print("No runs found.")
                return 0
            print(f"{'RUN ID':<14} {'PIPELINE':<24} {'STATUS':<10} {'DURATION':>14}  STARTED")
            for run in runs:
                print(f"{run.run_id:<14} {run.pipeline_name[:23]:<24} {run.status:<10} {run.duration_ms:>10.2f} ms  {run.started_at}")
            return 0
        if args.command == "report":
            run = store.get(args.run_id) if args.run_id else store.latest(args.pipeline)
            if run is None or (args.pipeline and run.pipeline_name != args.pipeline):
                print("Requested run was not found.", file=sys.stderr)
                return 2
            if args.format == "terminal":
                content = render_terminal(run)
            elif args.format == "json":
                content = render_json(run)
            else:
                content = render_html(run, store.list(run.pipeline_name, 20))
                output = Path(args.output or f"{run.pipeline_name.lower().replace(' ', '-')}-report.html")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(content, encoding="utf-8")
                print(f"HTML report written to {output.resolve()}")
                return 0
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(content, encoding="utf-8")
                print(f"Report written to {output.resolve()}")
            else:
                print(content)
            return 0
        if args.command == "compare":
            a, b = store.get(args.run_a), store.get(args.run_b)
            if not a or not b:
                print("One or both run IDs were not found.", file=sys.stderr)
                return 2
            if args.pipeline and (a.pipeline_name != args.pipeline or b.pipeline_name != args.pipeline):
                print("Run does not belong to the requested pipeline.", file=sys.stderr)
                return 2
            # Reuse Pipeline's comparison algorithm without creating a new history database.
            from .pipeline import Pipeline
            pipeline = Pipeline(a.pipeline_name, history=False, storage_dir=None)
            class _Store:
                def latest(self, _name):
                    return None

                def list(self, pipeline_name=None, limit=1000):
                    return [b, a]

                def get(self, run_id):
                    if run_id == a.run_id:
                        return a
                    if run_id == b.run_id:
                        return b
                    return None
            pipeline._store = _Store()
            print(pipeline.compare(a.run_id, b.run_id).explain())
            return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"stagewatch: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
