# API reference

## Public exports

- `Pipeline(name, **options)` — pipeline stages, history, inspection and analysis settings.
- `stage(pipeline, name=None)` — decorator shortcut.
- `Pipeline.add_stage(function, name=None)` — programmatic stage registration.
- `Pipeline.stage(name, input_data=None, has_input=True)` — context-manager stage.
- `Pipeline.record_stage(name, input_data, output_data, duration_ms=None)` — manually record a stage.
- `Pipeline.add_check(stage, check, message=..., severity='warning', target='output', code=...)` — custom predicate.
- `Pipeline.expect_range(stage, minimum=None, maximum=None, target='output', severity='warning')` — numeric bounds.
- `Pipeline.expect_shape(stage, shape, target='output', severity='warning')` — shape contract; `None` dimensions are wildcards.
- `Pipeline.expect_outlier_rate(stage, maximum_ratio, target='output', severity='warning')` — IQR outlier-rate contract.
- `Pipeline.run(data, metadata=None)` — execute registered stages in order.
- `Pipeline.history(limit=20)` — newest-first runs.
- `Pipeline.get_run(run_id)` — retrieve one run.
- `Pipeline.compare(run_a=None, run_b=None)` — compare latest two or explicit run IDs.
- `Pipeline.report(format='terminal', run_id=None, path=None)` — terminal/JSON/HTML report.
- `Pipeline.clear_history()` — remove local history for this pipeline.
- `inspect_value(value, ...)` — bounded summary without retaining raw input.
- `register_inspector(predicate, inspector)` — custom object inspection support.

## `Pipeline` options

| Option | Default | Meaning |
|---|---:|---|
| `storage_dir` | `.stagewatch` | SQLite history directory; `None` disables persistence |
| `history` | `True` | Persist history when storage is configured |
| `max_history` | `1000` | Maximum stored runs per pipeline |
| `deep_scan_limit_bytes` | `1_000_000` | Deep-scan size limit for optional integrations |
| `inspect_gpu` | `False` | Allow PyTorch GPU tensor scans |
| `size_change_threshold` | `1.0` | Relative footprint change warning threshold; `None` disables |
| `slowdown_threshold` | `1.0` | Relative slowdown against median baseline; `None` disables |
| `performance_window` | `5` | Number of recent successful runs to inspect |
| `performance_min_samples` | `3` | Baseline samples required before regression detection |
| `performance_min_duration_ms` | `5.0` | Ignore timings below this floor |
| `performance_comparison_threshold` | `0.10` | Relative duration increase for `compare()` |
| `detect_outliers` | `True` | Enable Tukey-IQR outlier findings |
| `outlier_iqr_multiplier` | `1.5` | Tukey fence multiplier |
| `outlier_min_count` | `3` | Minimum outlier values before a finding |
| `outlier_min_ratio` | `0.01` | Minimum fraction of outliers before a finding |
| `distribution_shift_threshold` | `3.0` | Mean-shift z-like threshold or spread-ratio threshold; `None` disables |
| `distribution_min_samples` | `3` | Baseline runs required for distribution checks |
| `aggregate_upstream_changes` | `True` | Aggregate likely downstream schema/size impacts |

## Numeric summaries

For supported numeric data, `inspect_value` may return `numeric_count`, `minimum`, `maximum`, `mean`, `std`, `median`, `q1`, `q3`, `iqr`, `outlier_count`, `outlier_ratio`, `outlier_lower_fence` and `outlier_upper_fence`. Scans are bounded; some summaries may be omitted when values exceed the configured scan limit or cannot be converted safely.

Pandas summaries also include `numeric_columns`, containing per-column statistical summaries. No raw numeric values are stored in report summaries.

## Run insights

`RunRecord.insights` contains machine-readable events such as:

- `root_cause` — earliest observable structural change.
- `upstream_impact` — downstream stage affected by the root change.
- `dynamic_dimension_accepted` — a declared wildcard shape changed as permitted.
- `dynamic_dimension_propagated` — a permitted dynamic dimension flowed through a downstream stage.

These are explanatory heuristics, not causal proofs.
