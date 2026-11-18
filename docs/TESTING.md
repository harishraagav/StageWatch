# Testing StageWatch 0.2.0a1

## Complete regression suite

Run from the project root:

```bash
python run_all_tests.py
```

The runner uses `unittest`, prepends `src/` to `sys.path`, and exercises core APIs, persistence, reports, CLI commands, privacy defaults, dynamic shape contracts, IQR outliers, distribution shifts, performance baselines, upstream-change aggregation, and backwards-compatible 0.1.x record loading. NumPy, Pandas and PyTorch tests run when those optional integrations are installed.

The current release source suite contains **57 tests**. The expected result in the build environment used for this bundle was 57 passed, 0 failed, 0 errors and 0 skipped with NumPy, Pandas and PyTorch installed. Results may vary by environment because optional integration tests skip when their package is absent.

The runner creates `test_output/` with terminal, JSON and HTML demo reports only after the suite passes.

## Three-pipeline integration validation

Run:

```bash
python run_three_pipeline_validation.py
```

This executes two runs for each of three deterministic synthetic scenarios: image processing, ML inference and data cleaning. It writes per-pipeline terminal/JSON/HTML reports, comparisons, summaries and SQLite history under `test_output/three_pipeline_validation/<timestamp>/`.

The script asserts that each pipeline completes all expected stages, records two runs, and has no failed stages or error-severity validation findings. Warning findings can be expected because the fixtures intentionally introduce batch/shape changes, outliers or data-quality conditions. Review `combined_summary.txt`, each `summary.json`, and each `report.html`; completion alone does not prove every statistical finding is correct.

## Build checks

With the `dev` extra installed:

```bash
python -m build
python -m twine check dist/*
ruff check src tests
```

## Suggested compatibility matrix

The GitHub Actions workflow is configured for Windows, macOS and Ubuntu across Python 3.10–3.14. A local green run does not replace successful remote CI on every matrix combination. PyTorch is not force-installed in the matrix because it is a large optional dependency; the PyTorch tests run wherever the extra is available.
