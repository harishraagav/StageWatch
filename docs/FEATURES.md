# Feature matrix

| Feature group | 0.2.0a1 status | Notes |
|---|---|---|
| Execution tracking | Included | Sequential decorator, context-manager and manual APIs; run IDs, order, durations and exceptions |
| Input/output inspection | Included | Built-in values and optional NumPy, Pandas, PyTorch support |
| Numerical summaries | Included | Min/max/mean/std/median/quartiles/IQR/outlier count when supported and within scan bounds |
| Basic anomaly detection | Included | NaN, infinity, missing/None and empty values; continuing counts deduplicated across stages |
| IQR outlier detection | Included | Configurable Tukey fences, count and ratio thresholds; Pandas columns handled independently |
| Distribution shift | Included | Baseline median mean/std comparisons after configured minimum samples |
| Shape contracts | Included | `None` wildcard dimensions for input/output shapes; dynamic footprint changes can be accepted |
| Root-cause-oriented changes | Included | First observable structural change and informational downstream propagation in sequential pipelines |
| Performance profiling | Included | Stage/run duration, median baselines, sample count and minimum-duration floor |
| Run comparison | Included | Stage state, schema, size, significant duration and finding changes |
| Local history | Included | SQLite persistence, retention limit and in-memory mode |
| Reports | Included | Terminal, JSON and standalone HTML with insights, findings and history |
| Custom validation | Included | Predicates, range, shape and outlier-rate contracts |
| CLI | Included | Version, history, report and compare commands |
| Privacy defaults | Included | Built-in paths never persist raw input/output payloads; no telemetry/network |

## Known limitations

- StageWatch is designed for sequential synchronous pipelines. Async, concurrent, branched and distributed orchestration are not a first-class 0.2.0a1 feature.
- Root-cause attribution is a heuristic based on observed stage boundaries, not proof of function-level causality.
- IQR outliers and distribution shifts are statistical signals; they may flag valid rare events or miss anomalies that are not distributional.
- Mixed-scale Pandas columns are assessed independently for IQR outliers and drift; non-numeric columns receive missing-value and structural checks, not numeric drift.
- Built-in Python nested-list shape inference applies only to rectangular list/tuple structures and is bounded by a maximum number of inspected items and depth.
- Array, tensor and tabular deep scans are limited by `deep_scan_limit_bytes`; GPU tensor scanning is opt-in.
- Python object footprint measurements are approximate and are not process RSS or allocator measurements.
- Exception strings and caller-provided run metadata may contain sensitive details; review them before sharing databases/reports.
