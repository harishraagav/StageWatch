from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stagewatch import Pipeline, inspect_value, register_inspector, stage


class StageWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_pipeline(self, name="test", **kwargs):
        return Pipeline(name, storage_dir=self.root / "history", **kwargs)

    def test_01_decorator_pipeline_tracks_and_passes_values(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def add_one(value):
            return value + 1

        @stage(pipeline)
        def double(value):
            return value * 2

        self.assertEqual(pipeline.run(4), 10)
        run = pipeline.history()[0]
        self.assertEqual([s.name for s in run.stages], ["add_one", "double"])
        self.assertEqual(run.status, "success")
        self.assertGreaterEqual(run.duration_ms, 0)

    def test_02_decorator_can_be_called_directly(self):
        pipeline = self.make_pipeline()

        @stage(pipeline, "plus")
        def plus(value, amount=2):
            return value + amount

        self.assertEqual(plus(3, amount=4), 7)
        self.assertEqual(pipeline.history()[0].stages[0].name, "plus")

    def test_03_execution_timing_and_stage_status(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run([1, 2, 3])
        record = pipeline.history()[0].stages[0]
        self.assertIn(record.status, {"success", "warning", "failed"})
        self.assertGreaterEqual(record.duration_ms, 0.0)
        self.assertTrue(record.started_at)
        self.assertTrue(record.finished_at)

    def test_04_exception_is_recorded_and_reraised(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def explode(value):
            raise RuntimeError("deliberate test failure")

        with self.assertRaisesRegex(RuntimeError, "deliberate test failure"):
            pipeline.run("input")
        run = pipeline.history()[0]
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.stages[0].status, "failed")
        self.assertEqual(run.stages[0].error_type, "RuntimeError")

    def test_05_inspection_handles_scalars_containers_and_none(self):
        scalar = inspect_value(float("nan"))
        self.assertEqual(scalar.get("nan_count"), 1)
        summary = inspect_value({"scores": [1, float("inf"), None], "empty": []})
        self.assertEqual(summary["inf_count"], 1)
        self.assertEqual(summary["none_count"], 1)
        self.assertIn("mapping_keys", summary)
        self.assertGreater(summary["estimated_size_bytes"], 0)

    def test_06_nan_inf_none_and_empty_findings(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def corrupt(_value):
            return [float("nan"), float("inf"), None]

        pipeline.run("source")
        codes = {f.code for f in pipeline.history()[0].stages[0].findings}
        self.assertTrue({"nan_detected", "infinity_detected", "none_values_detected"}.issubset(codes))
        self.assertEqual(pipeline.history()[0].stages[0].status, "warning")

    def test_07_empty_values_are_detected(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def empty(_value):
            return []

        pipeline.run(1)
        self.assertIn("empty_value", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_08_cross_run_schema_and_size_changes(self):
        pipeline = self.make_pipeline(size_change_threshold=0.1)

        @stage(pipeline)
        def passthrough(value):
            return value

        pipeline.run([1, 2])
        pipeline.run([1, 2, 3, 4, 5, 6])
        findings = pipeline.history()[0].stages[0].findings
        codes = {f.code for f in findings}
        self.assertIn("pipeline_input_changed", codes)
        self.assertTrue(findings[0].details.get("root_stage", "").startswith("pipeline input"))

    def test_09_performance_slowdown_rule_is_configurable(self):
        pipeline = self.make_pipeline(slowdown_threshold=0.5, performance_min_samples=1, performance_min_duration_ms=0)
        calls = {"count": 0}

        @stage(pipeline)
        def identity(value):
            calls["count"] += 1
            time.sleep(0.001 if calls["count"] == 1 else 0.03)
            return value

        pipeline.run(1)
        pipeline.run(1)
        self.assertIn("performance_regression", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_10_custom_boolean_and_string_checks(self):
        pipeline = self.make_pipeline()
        pipeline.add_check("validate", lambda value: len(value) == 2, message="Need two items", severity="error")
        pipeline.add_check("validate", lambda value: "contains forbidden value" if 99 in value else True, message="Forbidden", code="blocked")

        @stage(pipeline)
        def validate(value):
            return [1, 99, 3]

        pipeline.run([])
        findings = pipeline.history()[0].stages[0].findings
        self.assertTrue(any(f.code == "custom_check_failed" and f.severity == "error" for f in findings))
        self.assertTrue(any(f.code == "blocked" and "forbidden" in f.message for f in findings))

    def test_11_expect_range_helper(self):
        pipeline = self.make_pipeline()
        pipeline.expect_range("scale", minimum=0, maximum=1)

        @stage(pipeline)
        def scale(_value):
            return [0.2, 1.5]

        pipeline.run(None)
        self.assertIn("numeric_range_violation", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_12_context_manager_api(self):
        pipeline = self.make_pipeline()
        source = [1, 2]
        with pipeline.stage("transform", input_data=source) as tracked:
            tracked.set_output([2, 4])
        run = pipeline.history()[0]
        self.assertEqual(run.stages[0].name, "transform")
        self.assertEqual(run.stages[0].output_summary["length"], 2)

    def test_13_context_manager_records_failures(self):
        pipeline = self.make_pipeline()
        with self.assertRaisesRegex(ValueError, "bad stage"):
            with pipeline.stage("broken", input_data=3):
                raise ValueError("bad stage")
        self.assertEqual(pipeline.history()[0].status, "failed")

    def test_14_manual_record_stage_api(self):
        pipeline = self.make_pipeline()
        record = pipeline.record_stage("manual", {"a": 1}, {"a": 2}, duration_ms=1.2)
        self.assertEqual(record.name, "manual")
        self.assertEqual(pipeline.history()[0].stages[0].duration_ms, 1.2)

    def test_15_history_persists_and_retains_latest_n_runs(self):
        pipeline = self.make_pipeline(max_history=2)

        @stage(pipeline)
        def identity(value):
            return value

        ids = []
        for value in range(3):
            pipeline.run(value)
            ids.append(pipeline.history()[0].run_id)
        history = pipeline.history(limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].run_id, ids[-1])
        reopened = Pipeline("test", storage_dir=self.root / "history")
        self.assertEqual(len(reopened.history(limit=10)), 2)

    def test_16_run_comparison_reports_changes(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run([1, 2])
        pipeline.run([1, 2, 3, 4])
        comparison = pipeline.compare()
        self.assertEqual(comparison.run_b, pipeline.history()[0].run_id)
        self.assertTrue(comparison.stage_changes)
        self.assertIn("StageWatch comparison", comparison.explain())
        self.assertEqual(comparison.to_dict()["run_a"], comparison.run_a)

    def test_17_terminal_json_and_html_reports(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run({"safe": "metadata only"})
        terminal = pipeline.report()
        json_text = pipeline.report(format="json")
        self.assertIn("STAGEWATCH", terminal)
        self.assertEqual(json.loads(json_text)["pipeline_name"], "test")
        html_path = pipeline.report(format="html", path=self.root / "report.html")
        self.assertTrue(Path(html_path).exists())
        self.assertIn("Recent execution history", Path(html_path).read_text(encoding="utf-8"))

    def test_18_reports_can_be_exported_to_paths(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run(2)
        path = pipeline.report(format="json", path=self.root / "run.json")
        self.assertTrue(Path(path).exists())

    def test_19_cli_history_and_report(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run(5)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        db = str(pipeline.db_path)
        history = subprocess.run([sys.executable, "-m", "stagewatch.cli", "history", "--db", db], capture_output=True, text=True, env=env)
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn("PIPELINE", history.stdout)
        report = subprocess.run([sys.executable, "-m", "stagewatch.cli", "report", "--db", db, "--format", "json"], capture_output=True, text=True, env=env)
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertEqual(json.loads(report.stdout)["pipeline_name"], "test")

    def test_20_cli_compare(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run([1, 2])
        first = pipeline.history()[0].run_id
        pipeline.run([1, 2, 3])
        second = pipeline.history()[0].run_id
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        # Simulate a Windows console using a legacy code page such as CP1252.
        # CLI output should remain printable without requiring Unicode arrows.
        env["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run([sys.executable, "-m", "stagewatch.cli", "compare", first, second, "--db", str(pipeline.db_path)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("StageWatch comparison", result.stdout)

    def test_21_cli_escapes_unencodable_stage_names(self):
        pipeline = self.make_pipeline()

        @stage(pipeline, "学生")
        def identity(value):
            return value

        pipeline.run(7)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run(
            [sys.executable, "-m", "stagewatch.cli", "report", "--db", str(pipeline.db_path), "--format", "terminal"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(r"\u5b66\u751f", result.stdout)

    def test_22_raw_payload_is_not_persisted(self):
        pipeline = self.make_pipeline()
        secret_marker = "THIS_SHOULD_NEVER_BE_STORED_928471"

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run({"private": secret_marker})
        raw_db = Path(pipeline.db_path).read_bytes()
        self.assertNotIn(secret_marker.encode(), raw_db)
        report = pipeline.report(format="json")
        self.assertNotIn(secret_marker, report)

    def test_23_custom_inspector_registration(self):
        class CustomPacket:
            def __init__(self, count):
                self.count = count

        register_inspector(lambda item: isinstance(item, CustomPacket), lambda item, limit: {"length": item.count, "estimated_size_bytes": 123})
        summary = inspect_value(CustomPacket(7))
        self.assertEqual(summary["length"], 7)
        self.assertEqual(summary["estimated_size_bytes"], 123)

    def test_24_duplicate_stage_names_are_rejected(self):
        pipeline = self.make_pipeline()

        @stage(pipeline, "same")
        def first(value):
            return value

        with self.assertRaises(ValueError):
            @stage(pipeline, "same")
            def second(value):
                return value

    def test_25_memory_only_mode(self):
        pipeline = Pipeline("memory-only", storage_dir=None)

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run(1)
        pipeline.run(2)
        self.assertEqual(len(pipeline.history()), 2)
        self.assertTrue(pipeline.compare().stage_changes or pipeline.compare().summary["duration_b_ms"] >= 0)
        self.assertIsNone(pipeline.db_path)

    def test_26_numpy_inspection_when_available(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy optional extra is not installed")
        summary = inspect_value(np.array([1.0, np.nan, np.inf]))
        self.assertEqual(summary["nan_count"], 1)
        self.assertEqual(summary["inf_count"], 1)
        self.assertEqual(summary["shape"], [3])

    def test_28_pandas_dataframe_and_series_inspection_when_available(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Pandas optional extra is not installed")
        frame_summary = inspect_value(pd.DataFrame({"value": [1.0, None, 3.0]}))
        series_summary = inspect_value(pd.Series([1.0, None]))
        self.assertEqual(frame_summary.get("missing_count"), 1)
        self.assertEqual(series_summary.get("missing_count"), 1)
        self.assertEqual(series_summary.get("length"), 2)

    def test_30_torch_tensor_inspection_when_available(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch optional extra is not installed")
        summary = inspect_value(torch.tensor([1.0, float("nan"), float("inf")]))
        self.assertEqual(summary.get("nan_count"), 1)
        self.assertEqual(summary.get("inf_count"), 1)
        self.assertEqual(summary.get("shape"), [3])

    def test_29_history_database_can_be_removed_after_operations(self):
        """SQLite handles must be closed before Windows removes the temp folder."""
        from stagewatch.history import HistoryStore

        db_dir = self.root / "closable-history"
        db_dir.mkdir()
        db_path = db_dir / "closable.sqlite3"
        store = HistoryStore(db_path)

        @stage(Pipeline("closable", storage_dir=db_dir / "pipeline-history"))
        def identity(value):
            return value

        identity(123)
        store.list()
        store.delete_all()
        # On Windows an open SQLite handle causes this operation to fail.
        db_path.unlink()
        self.assertFalse(db_path.exists())

    def test_27_history_clear(self):
        pipeline = self.make_pipeline()

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run(3)
        removed = pipeline.clear_history()
        self.assertEqual(removed, 1)
        self.assertEqual(pipeline.history(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
