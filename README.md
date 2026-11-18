# StageWatch

[![Tests](https://github.com/harishraagav/StageWatch/actions/workflows/tests.yml/badge.svg)](https://github.com/harishraagav/StageWatch/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/harishraagav/StageWatch/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**Repository:** https://github.com/harishraagav/StageWatch  
**Issues and feature requests:** https://github.com/harishraagav/StageWatch/issues  

**The Python Pipeline Inspector.** Understand every stage of a Python data pipeline, detect suspicious numerical and structural changes, compare executions, and generate local reports.

**Author, developer and maintainer:** Harish Raagav K J  

> **Current release: 0.2.0 — Alpha.** This release adds dynamic shape contracts, IQR outlier detection, distribution-shift checks, robust performance baselines, upstream-change aggregation, and root-cause-oriented reporting. It is suitable for evaluation and integration testing; it is not a substitute for production monitoring or a correctness proof.

StageWatch is a local-first observability toolkit for sequential Python functions and data-processing pipelines. The core uses the Python standard library only. NumPy, Pandas and PyTorch support are optional extras.

## Why StageWatch?

When a pipeline's final result looks wrong, developers often inspect each function manually. StageWatch records stage execution, bounded input/output summaries, timings, validation findings and exceptions. It then compares current behaviour with recent runs to help locate the earliest observable change.

```text
load_rgb_image       SUCCESS      0.42 ms
resize_image         SUCCESS      0.18 ms
normalize_image      WARNING      0.61 ms  3 NaN values detected
model_inference      SUCCESS     18.42 ms
export               SUCCESS      1.21 ms
```

## Highlights

- **Stage execution tracking:** order, run IDs, timestamps, duration, status and exception capture.
- **Safe data inspection:** types, dimensions, dtype, footprint estimates, missing values and numerical summaries without retaining raw inputs/outputs.
- **Numerical anomaly checks:** NaN, infinity, `None`, missing values, empty values and Tukey-IQR statistical outliers.
- **Distribution shift:** compare output means and spreads against a median baseline from recent runs; Pandas numeric columns are checked independently.
- **Schema contracts:** declare expected shapes with wildcard dimensions such as `(None, 16)` for variable batch sizes.
- **Upstream-change aggregation:** report the earliest observable structural change and mark likely downstream propagation as informational instead of repeating the same warning at every stage.
- **Performance profiling:** per-stage and run duration, plus regression alerts using a median baseline and configurable sample/duration floors.
- **Run comparison and local history:** compare recent executions; retain history in SQLite or memory only.
- **Reports:** terminal, JSON and standalone HTML with pipeline insights, findings and run history.
- **Custom checks:** predicate checks, numeric range checks, shape contracts and outlier-rate contracts.
- **Multiple APIs:** decorators, context managers and manual recording.
- **CLI:** inspect history, render reports and compare run IDs.
- **Local-first privacy:** no telemetry, network calls, API keys or hosted service. Raw inputs and outputs are not persisted by built-in recording paths.

## Install

**Release status:** StageWatch 0.2.0 is packaged for evaluation but has not yet been published to PyPI. Install the included wheel from the complete release bundle:

```powershell
py -m pip install --upgrade --force-reinstall .\dist\stagewatch-0.2.0-py3-none-any.whl
```

After the maintainers publish the project, the intended PyPI installation command will be:

```bash
python -m pip install stagewatch
```

Optional integrations from this extracted source tree:

```bash
python -m pip install ".[numpy]"
python -m pip install ".[pandas]"
python -m pip install ".[torch]"
python -m pip install ".[all]"
```

After PyPI publication, the equivalent commands will use `stagewatch[numpy]`, `stagewatch[pandas]`, `stagewatch[torch]` or `stagewatch[all]`.

Core dependencies: **none**. Python: **3.10+**.

## Quick start

```python
from stagewatch import Pipeline, stage

pipeline = Pipeline("image-preprocessing")

@stage(pipeline)
def resize(image):
    return image[::2, ::2, :]

@stage(pipeline)
def normalize(image):
    return image.astype("float32") / 255.0

# Accept variable image height/width, but require three channels.
pipeline.expect_shape("resize", (None, None, 3))
pipeline.expect_shape("normalize", (None, None, 3))
pipeline.expect_range("normalize", minimum=0.0, maximum=1.0)

result = pipeline.run(image_array)
print(pipeline.report())
pipeline.report(format="html", path="artifacts/pipeline-report.html")
```

`Pipeline.run(data)` passes each registered stage's output to the next stage, in registration order. The first positional argument of each decorated stage is inspected as its input.

## Dynamic shape contracts

A `None` dimension is a wildcard. It explicitly declares that dimension as variable and avoids expected cross-run schema/footprint warnings for that contract.

```python
from stagewatch import Pipeline, stage

pipeline = Pipeline("batch-inference")
pipeline.expect_shape("prepare", (None, 16))
pipeline.expect_shape("predict", (None, 4))

@stage(pipeline, "prepare")
def prepare(batch):
    return batch

@stage(pipeline, "predict")
def predict(features):
    return model(features)

pipeline.run(batch_of_32)
pipeline.run(batch_of_128)  # batch-size change is allowed by the contracts
```

Contracts can target `input` or `output`:

```python
pipeline.expect_shape("prepare", (None, 16), target="input")
```

A mismatch in a fixed dimension generates `shape_contract_violation`. For regular nested Python lists/tuples, StageWatch infers rectangular shapes. Ragged nested sequences do not receive a rectangular shape contract summary.

## Anomaly and distribution settings

By default StageWatch:

- detects NaN, infinity, missing/None and empty values;
- applies Tukey's IQR rule with multiplier `1.5`;
- reports statistical outliers when at least 3 values and at least 1% of scanned numeric values are outliers;
- compares numeric output distribution against at least 3 recent successful observations per stage;
- checks distribution mean shift in baseline standard deviations and material spread changes.

Configure these choices:

```python
pipeline = Pipeline(
    "quality-check",
    detect_outliers=True,
    outlier_iqr_multiplier=1.5,
    outlier_min_count=3,
    outlier_min_ratio=0.01,
    distribution_shift_threshold=3.0,
    distribution_min_samples=3,
)
```

Use the built-in outlier-rate contract:

```python
pipeline.expect_outlier_rate(
    "validate_features",
    maximum_ratio=0.02,
    target="output",
    severity="warning",
)
```

Outlier and distribution-shift findings are statistical signals, not proof of bad data. They can be inappropriate for naturally heavy-tailed, multimodal or mixed-scale data. For DataFrames, StageWatch calculates IQR outliers and distribution shifts independently for each numeric column.

## Custom validation

```python
pipeline.expect_range("normalize", minimum=0.0, maximum=1.0)
pipeline.expect_shape("infer", (None, 4))
pipeline.expect_outlier_rate("infer", maximum_ratio=0.01)

pipeline.add_check(
    "validate_predictions",
    lambda values: values is not None and len(values) > 0,
    message="Predictions must not be empty",
    severity="error",
)
```

A custom check passes when it returns `True` or `None`. Returning `False` or a string creates a finding. A validator exception creates a `validator_error` finding and does not replace the pipeline's own exception handling.

## Performance baselines

StageWatch uses recent successful runs and their **median** stage duration rather than treating one previous timing as a reliable baseline.

```python
pipeline = Pipeline(
    "training-step",
    performance_window=7,
    performance_min_samples=3,
    performance_min_duration_ms=5.0,
    slowdown_threshold=1.0,
)
```

With these settings, regression checks wait for at least three baseline observations, ignore stage timings below 5 ms, and warn when the current stage is at least 100% slower than the median. Use `slowdown_threshold=None` to disable these checks. Very small timings are noisy and should not be treated as stable performance benchmarks.

## Root-cause-oriented findings

When a stage's output first changes while its input structure remains stable, StageWatch marks that as the earliest observable root stage. Later shape/size changes are grouped as `upstream_change_propagated` informational findings rather than repeated warnings.

This is a **heuristic for sequential pipelines**, not a causal debugger. It cannot prove why a function's behaviour changed, and independent changes in concurrent, branched or externally stateful workflows may require custom checks and manual investigation.

## Context-manager API

```python
pipeline = Pipeline("etl-job")
source = {"records": [1, 2, 3]}

with pipeline.stage("transform", input_data=source) as tracked:
    result = {"records": [x * 10 for x in source["records"]]}
    tracked.set_output(result)

print(pipeline.report())
```

If an exception escapes the context, StageWatch records the failed stage and allows the original exception to propagate.

## Manual recording API

```python
pipeline.record_stage("clean", raw_input, clean_output, duration_ms=2.4)
```

## Custom inspectors

```python
from stagewatch import register_inspector

class Image:
    def __init__(self, width, height):
        self.width, self.height = width, height

register_inspector(
    lambda value: isinstance(value, Image),
    lambda image, byte_limit: {
        "shape": [image.height, image.width],
        "estimated_size_bytes": image.width * image.height * 3,
    },
)
```

## Reports

```python
print(pipeline.report(format="terminal"))
pipeline.report(format="json", path="artifacts/run.json")
pipeline.report(format="html", path="artifacts/run.html")
```

- `terminal` returns readable text unless a path is provided.
- `json` returns JSON text unless a path is provided.
- `html` writes a standalone HTML report and returns its path.

## CLI

```bash
stagewatch --version
stagewatch history
stagewatch history --db .stagewatch/my-pipeline.sqlite3 --limit 10
stagewatch report --format terminal
stagewatch report --format json --output run.json
stagewatch report --format html --output report.html
stagewatch report --db .stagewatch/my-pipeline.sqlite3 --run-id RUN_ID
stagewatch compare RUN_ID_OLD RUN_ID_NEW --db .stagewatch/my-pipeline.sqlite3
```

Without `--db`, the CLI uses the only `*.sqlite3` database it finds in `.stagewatch/`. It requests an explicit path if zero or multiple databases are found.

## Local configuration

```python
pipeline = Pipeline(
    "my-pipeline",
    storage_dir=".stagewatch",          # SQLite directory; None disables persistence
    history=True,
    max_history=1000,
    deep_scan_limit_bytes=1_000_000,
    inspect_gpu=False,
    size_change_threshold=1.0,           # 100% footprint change; None disables
    slowdown_threshold=1.0,              # 100% slower than baseline median; None disables
    performance_window=5,
    performance_min_samples=3,
    performance_min_duration_ms=5.0,
    performance_comparison_threshold=0.10,
    detect_outliers=True,
    outlier_iqr_multiplier=1.5,
    outlier_min_count=3,
    outlier_min_ratio=0.01,
    distribution_shift_threshold=3.0,     # None disables
    distribution_min_samples=3,
    aggregate_upstream_changes=True,
)
```

Use `storage_dir=None` or `history=False` to keep history in memory only. `deep_scan_limit_bytes` bounds deep inspection for supported third-party arrays/tables/tensors. GPU tensor inspection is disabled by default because reading a device tensor can synchronize execution.

## Privacy and operational notes

- StageWatch does not send telemetry, make network requests or call external services.
- Built-in recording persists summaries and metadata, not raw input/output payloads.
- Run metadata is persisted as supplied. Do not put secrets, personal data or raw payloads in `metadata`.
- Exception messages can contain application data; inspect them before sharing reports or databases.
- Python object footprint estimates are approximate, not process RSS or exact allocator measurements.
- Inspections are best-effort and bounded; custom classes need a registered inspector for meaningful summaries.
- The package is synchronous and designed for sequential pipelines. Async/concurrent/branched orchestration is not a first-class 0.2.0 feature.

## Development and testing

From the extracted repository root:

```bash
python -m pip install -e ".[dev,numpy,pandas]"
python run_all_tests.py
python run_three_pipeline_validation.py
```

The first command installs the editable package plus development and optional test dependencies. The test runner uses `unittest` and creates sample reports under `test_output/`. The three-pipeline script uses deterministic synthetic data only; it makes no network requests.

See [INSTALL.md](INSTALL.md), [docs/API.md](docs/API.md), [docs/DETECTION.md](docs/DETECTION.md), [docs/TESTING.md](docs/TESTING.md), and [docs/PUBLISHING.md](docs/PUBLISHING.md).

## License

MIT. See [LICENSE](LICENSE).
