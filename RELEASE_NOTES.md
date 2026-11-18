# StageWatch 0.2.0 Release Notes

**StageWatch 0.2.0 — Alpha**

StageWatch 0.2.0 focuses on making pipeline findings more useful and reducing false-positive noise when data dimensions are expected to vary.

## Main additions

1. **Dynamic shape contracts** — use `pipeline.expect_shape("infer", (None, 16))` to allow a variable batch dimension while validating the fixed feature dimension.
2. **IQR outlier detection** — summaries include quartiles, IQR fences and outlier count/ratio. Findings are configurable and use Tukey's IQR method.
3. **Distribution-shift checks** — compare current numeric output against recent successful runs using a median baseline. Pandas columns are analysed independently.
4. **Robust performance baselines** — stage duration regression checks use multiple samples, a median and a minimum duration floor.
5. **Upstream-change aggregation** — the first observable structural change is emphasized; downstream impacts are informational instead of duplicated warnings.
6. **Richer reports** — terminal, JSON and HTML reports include run-level insights and root-stage context.
7. **Additional validation** — `expect_outlier_rate`, expanded regression tests and a refreshed synthetic three-pipeline validation script.

## Install from a built wheel

```powershell
py -m pip install --upgrade --force-reinstall .\dist\stagewatch-0.2.0-py3-none-any.whl
```

## Verify the package

```powershell
py -c "import stagewatch; print(stagewatch.__version__); print(stagewatch.__file__)"
py run_all_tests.py
py run_three_pipeline_validation.py
```

Expected package version: `0.2.0`.

## Release status

This is an alpha source release prepared for local evaluation and eventual public distribution. It has not been published to PyPI. Verify the package name, metadata, ownership, build artifacts and full CI matrix before publishing. Real-world production stability has not been certified.
