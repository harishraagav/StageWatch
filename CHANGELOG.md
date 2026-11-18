# Changelog

All notable StageWatch changes are documented here.

## 0.2.0a1 - 2026-11-18

### Added
- Rectangular shape inference for built-in nested lists and tuples.
- `Pipeline.expect_shape()` contracts with `None` wildcard dimensions, for input or output.
- Tukey-IQR outlier summaries and configurable outlier findings.
- Numerical distribution-shift analysis using recent successful run baselines.
- Per-numeric-column outlier and distribution summaries for Pandas DataFrames/Series.
- `Pipeline.expect_outlier_rate()` validation helper; non-numeric input now fails the measurable-rate contract rather than silently passing.
- Median-based performance regression baselines with a minimum sample count and minimum timing floor.
- Root-cause-oriented schema/input-change findings and downstream informational propagation findings.
- Deduplication of continuing anomaly counts, including re-detection after an anomaly has been cleared.
- Run-level insights in JSON and HTML reports; run status now reflects warning findings.
- Additional regression tests and a refreshed three-pipeline validation script.

### Changed
- Expected variable shape/footprint changes can be declared and are no longer automatically treated as schema regressions.
- Cross-run shape/size changes in sequential stages are aggregated to reduce cascaded warning noise.
- Performance comparisons ignore timings below the configured floor and use a median baseline for regression alerts.
- Pandas numeric statistics are calculated per column for outlier and drift analysis.
- RunRecord deserialization remains compatible with 0.1.x records that do not contain pipeline insights.

### Compatibility
- Python 3.10+.
- Core runtime dependencies remain empty.
- NumPy, Pandas and PyTorch remain optional integrations.
- Existing decorator, context-manager, manual recording, history, comparison, reporting and CLI interfaces are retained.

### Limitations
- Root-cause attribution is a sequential-pipeline heuristic, not proof of causality.
- IQR outlier and distribution-shift checks are statistical signals and may not suit every distribution.
- Async, concurrent and branched pipeline orchestration is not a first-class supported API.

## 0.1.1 - 2026-11-18

- Fixed SQLite connection lifecycle for Windows temporary-directory cleanup.
- Made CLI output resilient to legacy Windows console encodings.
- Added regression coverage for SQLite handle cleanup and unencodable stage names.

## 0.1.0 - 2026-11-18

- Initial public alpha implementation of pipeline execution tracking, inspection, validation, history, comparison, reports, optional integrations and CLI.
