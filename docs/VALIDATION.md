# StageWatch 0.2.0a1 validation record

This record captures the checks performed for the first public alpha pre-release. It does not certify production stability or statistical correctness for every workload.

## Maintainer Windows validation

Windows 11, Python 3.12.13, NumPy, Pandas and PyTorch CPU installed:

| Metric | Result |
|---|---:|
| Automated tests | 57 |
| Passed | 57 |
| Failures | 0 |
| Errors | 0 |
| Skipped | 0 |

Three synthetic pipeline scenarios also completed: image processing (NumPy), ML inference (PyTorch CPU) and data cleaning (Pandas). All completed without pipeline execution failures. Findings and warnings in these tests are intentional signals from crafted input data, not necessarily defects.

## GitHub Actions validation before the alpha metadata update

The CI run for commit a70261063c0f2359d6b09581ab20dfc7d53cd2c4 completed **16/16 jobs successfully**. Coverage included:

- Ubuntu, Windows and macOS runners;
- Python 3.10, 3.11, 3.12, 3.13 and 3.14;
- the complete regression suite;
- Ruff lint;
- wheel and source distribution builds;
- release artifact preflight;
- Twine metadata validation;
- a separate PyTorch optional-integration job and three-pipeline validation.

Workflow: https://github.com/harishraagav/StageWatch/actions/runs/44306625078

The 0.2.0a1 version metadata and release workflow are a subsequent change and must pass their own GitHub Actions run before publication.

## Local 0.2.0a1 validation

- 57 tests passed, with zero failures, zero errors and zero skips in the current environment.
- NumPy, Pandas and PyTorch CPU integration tests ran.
- All three synthetic pipeline scenarios completed without execution failures.
- Built wheel and source archive both identify version 0.2.0a1.
- Release preflight validated package name, version, author, maintainer, MIT license, Python floor, project URLs and required archive contents.
- Installed wheel in an isolated target and verified the imported package reports version 0.2.0a1.
- SHA-256 manifest matches both local distribution files.

## Not established by these checks

- PyTorch CUDA/GPU execution; tested PyTorch path was CPU-only.
- Production reliability, high concurrency, async/branched/distributed orchestration.
- Statistical precision/recall or calibration of outlier and distribution-shift findings across diverse real-world distributions.
- Successful PyPI upload; verify the publish workflow and install from PyPI after the GitHub prerelease is published.
