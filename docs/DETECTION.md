# Detection methods and interpretation

StageWatch 0.2.0 includes deterministic checks and statistical heuristics. Findings are evidence to investigate, not a guarantee that data is wrong.

## Deterministic checks

- NaN and infinity counts for scanned numeric arrays/tensors and built-in numeric containers.
- Missing-value counts for supported Pandas objects.
- `None` counts for built-in containers.
- Empty-value detection.
- Custom predicate, numeric range, shape and outlier-rate contracts.

## Tukey IQR outliers

For a numeric feature, StageWatch calculates the first quartile `Q1`, third quartile `Q3`, and `IQR = Q3 - Q1`. Fences are:

- lower fence: `Q1 - multiplier * IQR`
- upper fence: `Q3 + multiplier * IQR`

Values outside those fences are counted. By default, an outlier finding requires at least 3 values and at least 1% of scanned finite numeric values. Set `outlier_min_count`, `outlier_min_ratio`, `outlier_iqr_multiplier` or `detect_outliers=False` to tune or disable this check.

For Pandas DataFrames, StageWatch applies the IQR calculation independently to each numeric column. This avoids comparing values from unrelated scales in different columns.

## Distribution shift

StageWatch collects output summaries from recent successful executions of the same named stage. It compares the current mean with the median of baseline means, scaled by the median baseline standard deviation. It also checks the ratio between current and baseline spread. It requires `distribution_min_samples` baseline observations. Pandas numeric columns are compared independently.

This is a simple drift signal, not a full statistical hypothesis test. The threshold should be tuned for the nature, size and expected variability of the data.

## Performance regression

StageWatch compares a current stage duration with the median duration from recent successful executions. Regression detection waits for `performance_min_samples` baseline samples and ignores baseline/current timings below `performance_min_duration_ms`. The relative alert threshold is configured with `slowdown_threshold`; `1.0` means at least 100% slower than the baseline median.

The `compare()` output also filters small timing deltas by its configured threshold and minimum duration. Use a dedicated benchmark tool for rigorous microbenchmarking.

## Dynamic dimensions

`expect_shape` accepts `None` wildcard dimensions. Example: `(None, 128)` means any row/batch count is allowed but the second dimension must remain 128. When a declared dynamic shape changes, the corresponding expected shape/length and footprint changes are not treated as schema regressions. The contract itself is still enforced on every execution.

## Upstream aggregation

For a sequential pipeline, StageWatch records the earliest observable structural change and annotates later shape/size changes as likely propagated impacts. This reduces cascaded alerts, but it cannot prove causality or infer arbitrary dependency graphs. If a pipeline is branched or stateful, prefer explicit contracts and custom validation checks.
