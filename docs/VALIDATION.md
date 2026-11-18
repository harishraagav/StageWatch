# StageWatch 0.2.0 validation record

This file records checks performed while preparing the 0.2.0 source bundle. These checks are not a substitute for running CI on every supported operating system and Python version, and they do not certify production stability.

## Automated suite

Build environment: Python 3.13.5.

| Environment | Tests | Failures | Errors | Skips |
|---|---:|---:|---:|---:|
| NumPy + Pandas + PyTorch CPU available | 57 | 0 | 0 | 0 |
| Optional libraries hidden (`python -S`) | 57 | 0 | 0 | 8 |

The skipped tests in the core-only run are specifically optional NumPy, Pandas and PyTorch integration checks. The standard-library core remains usable without those packages.

## Three-pipeline integration scenarios

The deterministic, local-only validation script completed all three scenarios in both optional-backend and pure-Python modes.

| Scenario | Optional backend | Stages | Latest findings | Result |
|---|---|---:|---:|---|
| RGB image processing | NumPy | 4 | 0 | Completed |
| ML-style inference | PyTorch CPU | 5 | 1 | Completed with warning |
| Data cleaning | Pandas | 4 | 5 | Completed with warnings |
| RGB image processing fallback | Pure Python | 4 | 7 | Completed with warnings |
| ML-style inference fallback | Pure Python | 5 | 3 | Completed with warnings |
| Data cleaning fallback | Pure Python dictionaries | 4 | 9 | Completed with warnings |

Warnings in these scenarios are expected test signals, not execution failures. The inference scenario produces a potential IQR outlier finding in ReLU activations; such a finding is statistical evidence, not proof of invalid model output. The data-cleaning fixture deliberately includes NaNs, missing values and extreme values. The pure-Python scenarios use simpler summaries than their array/tabular backends.

## Build and install checks

- Built `stagewatch-0.2.0-py3-none-any.whl` and `stagewatch-0.2.0.tar.gz` using the configured setuptools backend.
- Inspected wheel archive contents and metadata version.
- Installed the wheel with `pip --no-deps --target ...` into an isolated directory.
- Verified the installed import path and `python -m stagewatch --version` output.
- Executed a smoke pipeline using the isolated installed wheel.
- Checked source archive contents include source, docs, tests and both top-level test scripts.

## Not yet verified

- A full remote GitHub Actions matrix across Windows, macOS and Linux and Python 3.10–3.14.
- PyTorch CUDA/GPU execution; the tested PyTorch build was CPU-only.
- A formal Twine check in this offline build environment (`twine` was not installed and could not be downloaded).
- Ruff lint in this offline build environment (`ruff` was not installed and could not be downloaded); the bundled CI workflow runs Ruff.
- A 0.2.0 run on Windows/macOS, including the full GitHub Actions matrix.
- Real production workloads, high concurrency, async/branched/distributed orchestration, or statistically calibrated anomaly quality.
- PyPI project-name availability or a public upload.

Run the included scripts on your target system and review the resulting reports before adopting StageWatch in production.
