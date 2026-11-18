from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewatch import Pipeline, inspect_value, stage
from stagewatch.models import RunRecord


class StageWatch020Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def memory_pipeline(self, name="v020", **kwargs):
        return Pipeline(name, storage_dir=None, **kwargs)

    def test_builtin_nested_lists_infer_rectangular_shapes(self):
        self.assertEqual(inspect_value([[1, 2, 3], [4, 5, 6]])["shape"], [2, 3])
        self.assertIsNone(inspect_value([[1, 2], [3]]) .get("shape"))

    def test_mapping_numeric_scalars_with_unrelated_units_do_not_share_iqr(self):
        summary = inspect_value({"height": 112, "width": 128, "channels": 3, "mean_luminance": 0.5})
        self.assertEqual(summary["outlier_count"], 0)
        self.assertEqual(summary["numeric_fields"], {})

    def test_numeric_vectors_inside_mapping_are_checked_independently(self):
        summary = inspect_value({"channel_means": [0.2, 0.3, 0.4, 0.5, 10.0], "width": 128, "height": 96})
        self.assertGreaterEqual(summary["outlier_count"], 1)
        self.assertIn("channel_means", summary["numeric_fields"])

    def test_numeric_inspection_has_distribution_statistics_and_iqr_outliers(self):
        summary = inspect_value([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000])
        self.assertEqual(summary["numeric_count"], 11)
        self.assertEqual(summary["outlier_count"], 1)
        self.assertGreater(summary["outlier_ratio"], 0)
        self.assertIn("median", summary)
        self.assertIn("std", summary)
        self.assertIn("q1", summary)
        self.assertIn("q3", summary)

    def test_outlier_detection_emits_finding_with_method_and_fences(self):
        pipeline = self.memory_pipeline(outlier_min_count=1, outlier_min_ratio=0.05)

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000])
        findings = pipeline.history()[0].stages[0].findings
        finding = next(item for item in findings if item.code == "statistical_outliers_detected")
        self.assertEqual(finding.details["method"], "Tukey IQR")
        self.assertIn("upper_fence", finding.details)

    def test_outlier_detection_can_be_disabled(self):
        pipeline = self.memory_pipeline(detect_outliers=False, outlier_min_count=1, outlier_min_ratio=0)

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000])
        codes = {item.code for item in pipeline.history()[0].stages[0].findings}
        self.assertNotIn("statistical_outliers_detected", codes)

    def test_dynamic_shape_contract_accepts_batch_dimension_variation(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy optional extra is not installed")
        pipeline = self.memory_pipeline()
        pipeline.expect_shape("identity", (None, 4), target="input")
        pipeline.expect_shape("identity", (None, 4), target="output")

        @stage(pipeline)
        def identity(value):
            return value.copy()

        pipeline.run(np.ones((3, 4), dtype=np.float32))
        pipeline.run(np.ones((9, 4), dtype=np.float32))
        latest = pipeline.history()[0]
        codes = {item.code for stage_record in latest.stages for item in stage_record.findings}
        self.assertNotIn("schema_changed", codes)
        self.assertNotIn("data_size_changed", codes)
        self.assertNotIn("pipeline_input_changed", codes)
        self.assertEqual(latest.status, "success")
        self.assertTrue(any(item["kind"] == "dynamic_dimension_accepted" for item in latest.insights))

    def test_dynamic_shape_contract_propagates_through_downstream_stages(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy optional extra is not installed")
        pipeline = self.memory_pipeline()
        pipeline.expect_shape("source", (None, 4), target="input")
        pipeline.expect_shape("source", (None, 4), target="output")

        @stage(pipeline)
        def source(value):
            return value.copy()

        @stage(pipeline)
        def downstream(value):
            return value + 1

        pipeline.run(np.ones((2, 4), dtype=np.float32))
        pipeline.run(np.ones((12, 4), dtype=np.float32))
        latest = pipeline.history()[0]
        codes = [finding.code for record in latest.stages for finding in record.findings]
        self.assertNotIn("schema_changed", codes)
        self.assertNotIn("pipeline_input_changed", codes)
        self.assertNotIn("upstream_change_propagated", codes)
        self.assertTrue(any(item["kind"] == "dynamic_dimension_propagated" for item in latest.insights))
        self.assertEqual(latest.status, "success")

    def test_shape_contract_violation_is_explicit(self):
        pipeline = self.memory_pipeline()
        pipeline.expect_shape("validate", (None, 4))

        @stage(pipeline)
        def validate(value):
            return value

        pipeline.run([[1, 2, 3]])
        findings = pipeline.history()[0].stages[0].findings
        self.assertTrue(any(item.code == "shape_contract_violation" for item in findings))

    def test_expect_outlier_rate_custom_validation(self):
        pipeline = self.memory_pipeline()
        pipeline.expect_outlier_rate("validate", maximum_ratio=0.01)

        @stage(pipeline)
        def validate(value):
            return value

        pipeline.run([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000])
        self.assertIn("outlier_rate_violation", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_expect_outlier_rate_rejects_non_numeric_input(self):
        pipeline = self.memory_pipeline()
        pipeline.expect_outlier_rate("validate", maximum_ratio=0.05)

        @stage(pipeline)
        def validate(value):
            return value

        pipeline.run(["alpha", "beta", "gamma"])
        findings = pipeline.history()[0].stages[0].findings
        self.assertIn("outlier_rate_violation", {finding.code for finding in findings})

    def test_distribution_shift_detected_after_baseline_window(self):
        pipeline = self.memory_pipeline(
            distribution_shift_threshold=3.0,
            distribution_min_samples=3,
            performance_min_duration_ms=0,
        )

        @stage(pipeline)
        def values(data):
            return data

        for _ in range(3):
            pipeline.run(list(range(20)))
        pipeline.run(list(range(100, 120)))
        latest = pipeline.history()[0]
        finding = next(f for f in latest.stages[0].findings if f.code == "distribution_shift")
        self.assertGreaterEqual(finding.details["columns"][0]["mean_shift_in_baseline_std"], 3.0)
        self.assertEqual(finding.details["columns"][0]["sample_count"], 3)

    def test_distribution_shift_waits_for_minimum_samples(self):
        pipeline = self.memory_pipeline(distribution_shift_threshold=2.0, distribution_min_samples=3)

        @stage(pipeline)
        def values(data):
            return data

        pipeline.run(list(range(10)))
        pipeline.run(list(range(100, 110)))
        self.assertNotIn("distribution_shift", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_performance_uses_median_baseline_after_minimum_samples(self):
        import time
        pipeline = self.memory_pipeline(
            slowdown_threshold=0.8,
            performance_window=5,
            performance_min_samples=3,
            performance_min_duration_ms=0,
        )
        calls = {"count": 0}

        @stage(pipeline)
        def worker(value):
            calls["count"] += 1
            time.sleep(0.002 if calls["count"] <= 3 else 0.025)
            return value

        for _ in range(3):
            pipeline.run(1)
        pipeline.run(1)
        finding = next(f for f in pipeline.history()[0].stages[0].findings if f.code == "performance_regression")
        self.assertEqual(finding.details["sample_count"], 3)
        self.assertEqual(finding.details["baseline_method"], "median of recent successful runs")

    def test_pandas_distribution_shift_is_reported_per_column(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Pandas optional extra is not installed")
        pipeline = self.memory_pipeline(distribution_min_samples=3, distribution_shift_threshold=3.0)

        @stage(pipeline)
        def frame(value):
            return value

        for _ in range(3):
            pipeline.run(pd.DataFrame({"temperature": list(range(20)), "pressure": [2.0] * 20}))
        pipeline.run(pd.DataFrame({"temperature": list(range(100, 120)), "pressure": [2.0] * 20}))
        finding = next(f for f in pipeline.history()[0].stages[0].findings if f.code == "distribution_shift")
        self.assertEqual([column["column"] for column in finding.details["columns"]], ["temperature"])

    def test_dataframe_outlier_detection_is_per_column_not_cross_column(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Pandas optional extra is not installed")
        frame = pd.DataFrame({"small_scale": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000], "large_scale": [10000] * 11})
        summary = inspect_value(frame)
        self.assertEqual(summary["numeric_columns"]["small_scale"]["outlier_count"], 1)
        self.assertEqual(summary["numeric_columns"]["large_scale"]["outlier_count"], 0)
        self.assertEqual(summary["outlier_count"], 1)

    def test_performance_noise_under_floor_is_ignored(self):
        import time
        pipeline = self.memory_pipeline(
            slowdown_threshold=0.1,
            performance_min_samples=2,
            performance_min_duration_ms=5.0,
        )
        calls = {"count": 0}

        @stage(pipeline)
        def tiny(value):
            calls["count"] += 1
            time.sleep(0.0002 if calls["count"] < 3 else 0.001)
            return value

        for _ in range(3):
            pipeline.run(1)
        self.assertNotIn("performance_regression", {f.code for f in pipeline.history()[0].stages[0].findings})

    def test_upstream_change_is_reported_once_then_downstream_as_info(self):
        pipeline = self.memory_pipeline()
        calls = {"count": 0}

        @stage(pipeline)
        def source(_value):
            calls["count"] += 1
            return [1, 2] if calls["count"] == 1 else [1, 2, 3, 4]

        @stage(pipeline)
        def downstream(value):
            return value

        pipeline.run("stable-source")
        pipeline.run("stable-source")
        latest = pipeline.history()[0]
        source_codes = {f.code for f in latest.stages[0].findings}
        downstream_codes = {f.code for f in latest.stages[1].findings}
        self.assertIn("schema_changed", source_codes)
        self.assertNotIn("schema_changed", downstream_codes)
        self.assertIn("upstream_change_propagated", downstream_codes)
        propagated = next(f for f in latest.stages[1].findings if f.code == "upstream_change_propagated")
        self.assertEqual(propagated.severity, "info")
        self.assertEqual(propagated.details["root_stage"], "source")
        self.assertEqual(latest.status, "warning")

    def test_independent_downstream_dtype_change_is_not_hidden_by_upstream_root(self):
        pipeline = self.memory_pipeline()
        calls = {"count": 0}

        @stage(pipeline)
        def source(_value):
            calls["count"] += 1
            return [1, 2] if calls["count"] == 1 else [1, 2, 3]

        @stage(pipeline)
        def downstream(value):
            if calls["count"] == 1:
                return value
            return {"values": value}

        pipeline.run("stable")
        pipeline.run("stable")
        latest = pipeline.history()[0]
        self.assertIn("schema_changed", {f.code for f in latest.stages[1].findings})

    def test_duplicate_anomalies_are_not_repeated_downstream(self):
        pipeline = self.memory_pipeline()

        @stage(pipeline)
        def introduce(_value):
            return [1, None, 3]

        @stage(pipeline)
        def pass_through(value):
            return value

        pipeline.run("seed")
        latest = pipeline.history()[0]
        findings = [f for record in latest.stages for f in record.findings if f.code == "none_values_detected"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].location, "output")

    def test_info_only_downstream_findings_do_not_warn_stage(self):
        calls = {"count": 0}
        pipeline = self.memory_pipeline()

        @stage(pipeline)
        def source(_value):
            calls["count"] += 1
            return [1, 2] if calls["count"] == 1 else [1, 2, 3]

        @stage(pipeline)
        def downstream(value):
            return value

        pipeline.run("stable")
        pipeline.run("stable")
        latest = pipeline.history()[0]
        downstream_record = latest.stages[1]
        self.assertIn("upstream_change_propagated", {f.code for f in downstream_record.findings})
        self.assertEqual(downstream_record.status, "success")

    def test_html_report_contains_insights_panel_and_warning_status(self):
        calls = {"count": 0}
        pipeline = self.memory_pipeline()

        @stage(pipeline)
        def variable(_value):
            calls["count"] += 1
            return [1, 2] if calls["count"] == 1 else [1, 2, 3]

        pipeline.run("stable")
        pipeline.run("stable")
        report_path = pipeline.report(format="html", path=self.root / "v020-report.html")
        report = Path(report_path).read_text(encoding="utf-8")
        self.assertIn("Root-cause and pipeline insights", report)
        self.assertIn("WARNING", report)

    def test_old_run_record_without_insights_remains_readable(self):
        data = {
            "run_id": "legacy", "pipeline_name": "old", "status": "success",
            "started_at": "2025-01-01T00:00:00+00:00", "finished_at": "2025-01-01T00:00:01+00:00",
            "duration_ms": 1.0, "stages": [], "metadata": {},
        }
        record = RunRecord.from_dict(data)
        self.assertEqual(record.insights, [])
        self.assertEqual(record.run_id, "legacy")

    def test_no_raw_payload_in_reports_or_history(self):
        pipeline = self.memory_pipeline()
        secret = "private-marker-0.2.0-should-not-appear"

        @stage(pipeline)
        def identity(value):
            return value

        pipeline.run({"customer_note": secret})
        self.assertNotIn(secret, pipeline.report(format="json"))
        html_path = pipeline.report(format="html", path=self.root / "private-report.html")
        self.assertNotIn(secret, Path(html_path).read_text(encoding="utf-8"))

    def test_custom_iqr_multiplier_is_used(self):
        strict = inspect_value([0, 1, 2, 3, 4, 5, 10], outlier_iqr_multiplier=1.5)
        permissive = inspect_value([0, 1, 2, 3, 4, 5, 10], outlier_iqr_multiplier=3.0)
        self.assertGreaterEqual(strict["outlier_count"], permissive["outlier_count"])

    def test_cleared_anomaly_can_be_detected_again_downstream(self):
        pipeline = self.memory_pipeline()
        calls = {"count": 0}

        @stage(pipeline)
        def introduce(_value):
            calls["count"] += 1
            return [1, None] if calls["count"] in {1, 3} else [1, 2]

        pipeline.run("a")
        pipeline.run("b")
        pipeline.run("c")
        latest = pipeline.history()[0]
        self.assertIn("none_values_detected", {f.code for f in latest.stages[0].findings})

    def test_pandas_nullable_numeric_column_can_be_inspected(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Pandas optional extra is not installed")
        frame = pd.DataFrame({"count": pd.Series([1, None, 3], dtype="Int64")})
        summary = inspect_value(frame)
        self.assertEqual(summary["missing_count"], 1)
        self.assertEqual(summary["numeric_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
