# Install and test StageWatch 0.2.0a1

StageWatch 0.2.0a1 is an alpha release bundle for local evaluation. The core package has no mandatory runtime dependencies. NumPy, Pandas and PyTorch integrations are optional.

## Windows (PowerShell or Command Prompt)

1. Extract `StageWatch_0.2.0a1_release_bundle.zip`.
2. Open a terminal in the extracted `StageWatch-0.2.0a1` folder (the folder containing `pyproject.toml`).
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   In Command Prompt, use `\.venv\Scripts\activate.bat` instead.

4. Install the included wheel:

   ```powershell
   python -m pip install --upgrade --force-reinstall .\dist\stagewatch-0.2.0a1-py3-none-any.whl
   ```

5. Confirm the installed version and location:

   ```powershell
   python -c "import stagewatch; print(stagewatch.__version__); print(stagewatch.__file__)"
   ```

6. Run the complete automated suite:

   ```powershell
   python run_all_tests.py
   ```

7. Run the three realistic synthetic pipeline scenarios:

   ```powershell
   python run_three_pipeline_validation.py
   ```

8. Try the included basic example:

   ```powershell
   python examples\basic_pipeline.py
   ```

The two test scripts use the source tree in this release folder, so they test the files you extracted rather than silently using an older installed copy. The three-pipeline validation script uses local synthetic data; it does not download datasets or call external APIs.

## macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade --force-reinstall ./dist/stagewatch-0.2.0a1-py3-none-any.whl
python -c "import stagewatch; print(stagewatch.__version__); print(stagewatch.__file__)"
python run_all_tests.py
python run_three_pipeline_validation.py
python examples/basic_pipeline.py
```

## Install optional integrations

Install only the integrations you need:

```bash
python -m pip install --pre "stagewatch[numpy]"
python -m pip install --pre "stagewatch[pandas]"
python -m pip install --pre "stagewatch[torch]"
python -m pip install --pre "stagewatch[all]"
```

In the release source folder, install optional extras from source with `python -m pip install -e ".[numpy,pandas]"` (or add `torch`). The all-in-one test runner automatically runs optional integration tests when the relevant libraries are installed and reports a skip when an optional library is absent.

## Build from source

With the build extra installed:

```bash
python -m pip install -e ".[dev]"
python -m build
python -m twine check dist/*
```

## Test outputs

`run_all_tests.py` creates `test_output/` with terminal, JSON and HTML demo reports plus a local SQLite history database.

`run_three_pipeline_validation.py` creates timestamped reports, comparisons, summaries and SQLite history under `test_output/three_pipeline_validation/` for:

- RGB image processing;
- NumPy/PyTorch-style ML inference (prefers PyTorch, then NumPy, then pure Python);
- Pandas-style data cleaning (uses Pandas when installed, otherwise pure Python).

These are synthetic integration scenarios, not production workload benchmarks. Warnings are expected where the script deliberately introduces outliers or statistical changes.
