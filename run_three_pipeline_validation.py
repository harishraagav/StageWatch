#!/usr/bin/env python3
"""Run three realistic, fully local StageWatch pipeline evaluations.

Run from the StageWatch project root (the directory containing pyproject.toml):
    python run_three_pipeline_validation.py

The script uses synthetic in-memory data only. It does not download datasets,
call APIs, or modify project source files. Reports and a SQLite history database
are written to test_output/three_pipeline_validation/<timestamp>/.

Optional backends are detected automatically:
- Image pipeline: NumPy when available, otherwise pure Python lists.
- ML inference: PyTorch when available, otherwise NumPy, otherwise pure Python.
- Data cleaning: Pandas when available, otherwise pure Python dictionaries.
"""
from __future__ import annotations

import json
import math
import platform
import random
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_DIR = PROJECT_ROOT / "src"
if SOURCE_DIR.is_dir():
    # Prefer the source tree in this release folder so the script also works
    # before a local install, and cannot accidentally validate an older wheel.
    sys.path.insert(0, str(SOURCE_DIR))

try:
    import stagewatch
    from stagewatch import Pipeline, stage
except ImportError as exc:  # pragma: no cover - environment-specific help
    print("ERROR: StageWatch is not importable in this Python environment.")
    print("Activate the package's virtual environment, then run:")
    print("  python -m pip install -e .")
    print("or install the wheel from dist/:")
    print("  python -m pip install --force-reinstall .\\dist\\stagewatch-0.2.0-py3-none-any.whl")
    raise SystemExit(2) from exc

# Optional integrations. The test remains runnable without any of them.
try:
    import numpy as np
except Exception:  # pragma: no cover - depends on user's environment
    np = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - depends on user's environment
    pd = None

try:
    import torch
except Exception:  # pragma: no cover - depends on user's environment
    torch = None


TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_utc")
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "three_pipeline_validation" / TIMESTAMP


def _version(module: Any) -> str | None:
    return getattr(module, "__version__", "available") if module is not None else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _latest_run(pipeline: Pipeline):
    runs = pipeline.history(limit=1)
    if not runs:
        raise RuntimeError(f"StageWatch did not persist a run for {pipeline.name!r}")
    return runs[0]


def _save_pipeline_artifacts(pipeline: Pipeline, output_dir: Path, expected_stages: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest = _latest_run(pipeline)
    if len(latest.stages) != expected_stages:
        raise AssertionError(
            f"{pipeline.name}: expected {expected_stages} stages, got {len(latest.stages)}"
        )
    if len(pipeline.history(limit=10)) != 2:
        raise AssertionError(f"{pipeline.name}: expected two recorded runs")
    failed_stages = [record.name for record in latest.stages if record.status == "failed"]
    if failed_stages:
        raise AssertionError(f"{pipeline.name}: failed stages: {failed_stages}")
    error_findings = [
        (record.name, finding.message)
        for record in latest.stages
        for finding in record.findings
        if finding.severity == "error"
    ]
    if error_findings:
        raise AssertionError(f"{pipeline.name}: validation errors: {error_findings}")

    terminal_report = pipeline.report(format="terminal")
    if not isinstance(terminal_report, str):
        terminal_report = str(terminal_report)
    (output_dir / "report.txt").write_text(terminal_report, encoding="utf-8")
    pipeline.report(format="json", path=output_dir / "report.json")
    pipeline.report(format="html", path=output_dir / "report.html")

    comparison = pipeline.compare()
    (output_dir / "comparison.txt").write_text(comparison.explain() + "\n", encoding="utf-8")
    _write_json(output_dir / "comparison.json", comparison.to_dict())

    history = pipeline.history(limit=10)
    summary = {
        "pipeline": pipeline.name,
        "latest_run_id": latest.run_id,
        "latest_status": latest.status,
        "latest_duration_ms": latest.duration_ms,
        "stage_count": len(latest.stages),
        "stage_statuses": {record.name: record.status for record in latest.stages},
        "finding_count": sum(len(record.findings) for record in latest.stages),
        "findings": [
            {
                "stage": record.name,
                "code": finding.code,
                "severity": finding.severity,
                "message": finding.message,
                "location": finding.location,
            }
            for record in latest.stages
            for finding in record.findings
        ],
        "history_runs": len(history),
        "comparison_stage_changes": comparison.stage_changes,
        "artifacts": {
            "terminal": str((output_dir / "report.txt").relative_to(PROJECT_ROOT)),
            "json": str((output_dir / "report.json").relative_to(PROJECT_ROOT)),
            "html": str((output_dir / "report.html").relative_to(PROJECT_ROOT)),
            "comparison": str((output_dir / "comparison.txt").relative_to(PROJECT_ROOT)),
        },
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def run_image_processing(output_root: Path) -> dict[str, Any]:
    """Synthetic RGB image pipeline: load -> resize -> normalize -> summarize."""
    print("\n[1/3] IMAGE-PROCESSING PIPELINE")
    backend = "NumPy" if np is not None else "pure Python"
    print(f"  Backend: {backend}")

    pipeline = Pipeline(
        "real-world-image-processing",
        storage_dir=output_root / "history",
        max_history=20,
        size_change_threshold=0.25,
        slowdown_threshold=None,
        outlier_min_count=1,
        outlier_min_ratio=0.01,
    )

    # The first dimension is image height/width; channel count is fixed.
    pipeline.expect_shape("load_rgb_image", (None, None, 3))
    pipeline.expect_shape("resize_image", (None, None, 3))
    pipeline.expect_shape("normalize_image", (None, None, 3))

    def make_image(spec: dict[str, int]):
        height, width, seed = spec["height"], spec["width"], spec["seed"]
        if np is not None:
            rng = np.random.default_rng(seed)
            return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
        return [
            [
                [
                    (x * 3 + y * 5 + seed) % 256,
                    (x * 7 + y * 2 + seed * 3) % 256,
                    (x * 2 + y * 11 + seed * 5) % 256,
                ]
                for x in range(width)
            ]
            for y in range(height)
        ]

    @stage(pipeline, "load_rgb_image")
    def load_rgb_image(spec: dict[str, int]):
        return make_image(spec)

    @stage(pipeline, "resize_image")
    def resize_image(image: Any):
        if np is not None and isinstance(image, np.ndarray):
            return image[::2, ::2, :]
        return [row[::2] for row in image[::2]]

    @stage(pipeline, "normalize_image")
    def normalize_image(image: Any):
        if np is not None and isinstance(image, np.ndarray):
            return image.astype(np.float32) / 255.0
        return [[[channel / 255.0 for channel in pixel] for pixel in row] for row in image]

    @stage(pipeline, "extract_image_metrics")
    def extract_image_metrics(image: Any):
        if np is not None and isinstance(image, np.ndarray):
            channel_means = image.mean(axis=(0, 1))
            luminance = image.mean(axis=2)
            return {
                "height": int(image.shape[0]),
                "width": int(image.shape[1]),
                "channels": int(image.shape[2]),
                "channel_means": [float(x) for x in channel_means],
                "mean_luminance": float(luminance.mean()),
                "contrast_stddev": float(luminance.std()),
            }
        channels = [channel for row in image for pixel in row for channel in pixel]
        pixel_count = max(1, len(image) * len(image[0]))
        channel_means = [
            sum(pixel[c] for row in image for pixel in row) / pixel_count for c in range(3)
        ]
        luminance = [sum(pixel) / 3.0 for row in image for pixel in row]
        mean_luminance = sum(luminance) / max(1, len(luminance))
        variance = sum((value - mean_luminance) ** 2 for value in luminance) / max(1, len(luminance))
        return {
            "height": len(image),
            "width": len(image[0]) if image else 0,
            "channels": 3,
            "channel_means": channel_means,
            "mean_luminance": mean_luminance,
            "contrast_stddev": math.sqrt(variance),
        }

    pipeline.expect_range("normalize_image", minimum=0.0, maximum=1.0)

    # Two input resolutions exercise cross-run shape/footprint comparison.
    pipeline.run({"height": 80, "width": 96, "seed": 7}, metadata={"scenario": "baseline", "synthetic": True})
    pipeline.run({"height": 112, "width": 128, "seed": 11}, metadata={"scenario": "larger_image", "synthetic": True})

    summary = _save_pipeline_artifacts(pipeline, output_root, expected_stages=4)
    print(f"  Latest run: {summary['latest_status']} | stages={summary['stage_count']} | findings={summary['finding_count']}")
    print(f"  Comparison changes: {len(summary['comparison_stage_changes'])}")
    return summary


def run_ml_inference(output_root: Path) -> dict[str, Any]:
    """Synthetic feed-forward inference pipeline with optional Torch/NumPy backend."""
    print("\n[2/3] MACHINE-LEARNING INFERENCE PIPELINE")
    if torch is not None:
        backend = "PyTorch (CPU)"
    elif np is not None:
        backend = "NumPy"
    else:
        backend = "pure Python"
    print(f"  Backend: {backend}")

    pipeline = Pipeline(
        "real-world-ml-inference",
        storage_dir=output_root / "history",
        max_history=20,
        size_change_threshold=0.20,
        slowdown_threshold=None,
        outlier_min_count=3,
        outlier_min_ratio=0.01,
    )

    # Variable batch size is expected; feature/class dimensions are fixed.
    pipeline.expect_shape("prepare_features", (None, 16))
    pipeline.expect_shape("dense_relu", (None, 12))
    pipeline.expect_shape("dense_logits", (None, 4))
    pipeline.expect_shape("softmax", (None, 4))

    if torch is not None:
        generator = torch.Generator(device="cpu").manual_seed(2026)
        weights_1 = torch.randn((16, 12), generator=generator) * 0.15
        weights_2 = torch.randn((12, 4), generator=generator) * 0.15
    elif np is not None:
        rng_weights = np.random.default_rng(2026)
        weights_1 = rng_weights.normal(0.0, 0.15, size=(16, 12)).astype(np.float32)
        weights_2 = rng_weights.normal(0.0, 0.15, size=(12, 4)).astype(np.float32)
    else:
        weights_1 = [[math.sin(i * 0.7 + j) * 0.15 for j in range(12)] for i in range(16)]
        weights_2 = [[math.cos(i * 0.4 + j * 0.3) * 0.15 for j in range(4)] for i in range(12)]

    @stage(pipeline, "prepare_features")
    def prepare_features(request: dict[str, int]):
        rows, seed = request["batch_size"], request["seed"]
        if torch is not None:
            gen = torch.Generator(device="cpu").manual_seed(seed)
            return torch.randn((rows, 16), generator=gen)
        if np is not None:
            return np.random.default_rng(seed).normal(0.0, 1.0, size=(rows, 16)).astype(np.float32)
        rng = random.Random(seed)
        return [[rng.uniform(-1.0, 1.0) for _ in range(16)] for _ in range(rows)]

    @stage(pipeline, "dense_relu")
    def dense_relu(features: Any):
        if torch is not None and isinstance(features, torch.Tensor):
            return torch.relu(features @ weights_1)
        if np is not None and isinstance(features, np.ndarray):
            return np.maximum(features @ weights_1, 0.0)
        result = []
        for row in features:
            result.append([
                max(0.0, sum(row[i] * weights_1[i][j] for i in range(16)))
                for j in range(12)
            ])
        return result

    @stage(pipeline, "dense_logits")
    def dense_logits(hidden: Any):
        if torch is not None and isinstance(hidden, torch.Tensor):
            return hidden @ weights_2
        if np is not None and isinstance(hidden, np.ndarray):
            return hidden @ weights_2
        return [
            [sum(row[i] * weights_2[i][j] for i in range(12)) for j in range(4)]
            for row in hidden
        ]

    @stage(pipeline, "softmax")
    def softmax(logits: Any):
        if torch is not None and isinstance(logits, torch.Tensor):
            return torch.softmax(logits, dim=1)
        if np is not None and isinstance(logits, np.ndarray):
            shifted = logits - logits.max(axis=1, keepdims=True)
            exp_values = np.exp(shifted)
            return exp_values / exp_values.sum(axis=1, keepdims=True)
        probabilities = []
        for row in logits:
            shifted = [value - max(row) for value in row]
            exp_values = [math.exp(value) for value in shifted]
            total = sum(exp_values)
            probabilities.append([value / total for value in exp_values])
        return probabilities

    def probabilities_are_valid(value: Any) -> bool:
        if torch is not None and isinstance(value, torch.Tensor):
            return bool(torch.isfinite(value).all().item() and torch.allclose(
                value.sum(dim=1), torch.ones(value.shape[0]), atol=1e-5
            ))
        if np is not None and isinstance(value, np.ndarray):
            return bool(np.isfinite(value).all() and np.allclose(value.sum(axis=1), 1.0, atol=1e-5))
        return all(
            all(math.isfinite(item) and 0.0 <= item <= 1.0 for item in row)
            and abs(sum(row) - 1.0) <= 1e-5
            for row in value
        )

    @stage(pipeline, "decode_predictions")
    def decode_predictions(probabilities: Any):
        if torch is not None and isinstance(probabilities, torch.Tensor):
            confidence, predicted_class = probabilities.max(dim=1)
            return {
                "sample_count": int(probabilities.shape[0]),
                "predicted_classes": predicted_class.tolist(),
                "confidence_mean": float(confidence.mean().item()),
                "confidence_min": float(confidence.min().item()),
                "confidence_max": float(confidence.max().item()),
            }
        if np is not None and isinstance(probabilities, np.ndarray):
            confidence = probabilities.max(axis=1)
            return {
                "sample_count": int(probabilities.shape[0]),
                "predicted_classes": probabilities.argmax(axis=1).tolist(),
                "confidence_mean": float(confidence.mean()),
                "confidence_min": float(confidence.min()),
                "confidence_max": float(confidence.max()),
            }
        confidence = [max(row) for row in probabilities]
        return {
            "sample_count": len(probabilities),
            "predicted_classes": [row.index(max(row)) for row in probabilities],
            "confidence_mean": sum(confidence) / len(confidence),
            "confidence_min": min(confidence),
            "confidence_max": max(confidence),
        }

    pipeline.add_check(
        "softmax",
        probabilities_are_valid,
        message="Softmax rows must be finite probabilities summing to 1",
        severity="error",
        code="invalid_probability_distribution",
    )
    pipeline.expect_range("softmax", minimum=0.0, maximum=1.0)

    pipeline.run({"batch_size": 32, "seed": 17}, metadata={"scenario": "baseline", "synthetic": True, "backend": backend})
    pipeline.run({"batch_size": 48, "seed": 23}, metadata={"scenario": "larger_batch", "synthetic": True, "backend": backend})

    summary = _save_pipeline_artifacts(pipeline, output_root, expected_stages=5)
    print(f"  Latest run: {summary['latest_status']} | stages={summary['stage_count']} | findings={summary['finding_count']}")
    print(f"  Comparison changes: {len(summary['comparison_stage_changes'])}")
    return summary


def _base_customer_rows(extra_row: bool = False) -> list[dict[str, Any]]:
    rows = [
        {"customer_id": 101, "age": 24, "annual_income": 42000.0, "city": "Chennai"},
        {"customer_id": 102, "age": 31, "annual_income": 68000.0, "city": "Bengaluru"},
        {"customer_id": 103, "age": None, "annual_income": 51000.0, "city": "Chennai"},
        {"customer_id": 104, "age": 45, "annual_income": None, "city": "Hyderabad"},
        {"customer_id": 105, "age": 29, "annual_income": 59000.0, "city": None},
        {"customer_id": 106, "age": 38, "annual_income": 91000.0, "city": "Mumbai"},
        {"customer_id": 107, "age": 52, "annual_income": 125000.0, "city": "Chennai"},
        {"customer_id": 108, "age": 19, "annual_income": 28000.0, "city": "Pune"},
        {"customer_id": 109, "age": 61, "annual_income": 490000.0, "city": "Delhi"},
        {"customer_id": 110, "age": 34, "annual_income": 74000.0, "city": "Bengaluru"},
    ]
    # Deliberate duplicate to exercise deduplication.
    rows.append(dict(rows[1]))
    if extra_row:
        rows.append({"customer_id": 111, "age": 42, "annual_income": 83000.0, "city": "Kochi"})
        rows.append({"customer_id": 112, "age": 0, "annual_income": 650000.0, "city": "Chennai"})
    return rows


def run_data_cleaning(output_root: Path) -> dict[str, Any]:
    """Dirty customer dataset pipeline: deduplicate -> impute -> cap -> engineer."""
    print("\n[3/3] DATA-CLEANING PIPELINE")
    backend = "Pandas" if pd is not None else "pure Python dictionaries"
    print(f"  Backend: {backend}")

    pipeline = Pipeline(
        "real-world-data-cleaning",
        storage_dir=output_root / "history",
        max_history=20,
        size_change_threshold=0.25,
        slowdown_threshold=None,
        outlier_min_count=1,
        outlier_min_ratio=0.01,
    )

    # Pandas frames have variable row counts but stable, declared column counts.
    if pd is not None:
        for stage_name in ("remove_duplicate_rows", "impute_missing_values", "cap_extreme_values"):
            pipeline.expect_shape(stage_name, (None, 4), target="input")
            pipeline.expect_shape(stage_name, (None, 4), target="output")
        pipeline.expect_shape("engineer_clean_features", (None, 4), target="input")
        pipeline.expect_shape("engineer_clean_features", (None, 6), target="output")

    def make_dataset(extra_row: bool):
        rows = _base_customer_rows(extra_row=extra_row)
        return pd.DataFrame(rows) if pd is not None else rows

    def no_missing_values(data: Any) -> bool:
        if pd is not None and isinstance(data, pd.DataFrame):
            return not bool(data.isna().any().any())
        return all(value is not None for row in data for value in row.values())

    def unique_customer_ids(data: Any) -> bool:
        if pd is not None and isinstance(data, pd.DataFrame):
            return bool(data["customer_id"].is_unique)
        identifiers = [row["customer_id"] for row in data]
        return len(identifiers) == len(set(identifiers))

    @stage(pipeline, "remove_duplicate_rows")
    def remove_duplicate_rows(data: Any):
        if pd is not None and isinstance(data, pd.DataFrame):
            return data.drop_duplicates().reset_index(drop=True)
        seen = set()
        result = []
        for row in data:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                result.append(dict(row))
        return result

    @stage(pipeline, "impute_missing_values")
    def impute_missing_values(data: Any):
        if pd is not None and isinstance(data, pd.DataFrame):
            result = data.copy()
            for column in ("age", "annual_income"):
                result[column] = result[column].fillna(result[column].median())
            result["city"] = result["city"].fillna("unknown")
            return result
        result = [dict(row) for row in data]
        for column in ("age", "annual_income"):
            available = sorted(float(row[column]) for row in result if row[column] is not None)
            middle = len(available) // 2
            median = available[middle] if len(available) % 2 else (available[middle - 1] + available[middle]) / 2
            for row in result:
                if row[column] is None:
                    row[column] = median
        for row in result:
            if row["city"] is None:
                row["city"] = "unknown"
        return result

    @stage(pipeline, "cap_extreme_values")
    def cap_extreme_values(data: Any):
        if pd is not None and isinstance(data, pd.DataFrame):
            result = data.copy()
            result["age"] = result["age"].clip(lower=18, upper=85)
            result["annual_income"] = result["annual_income"].clip(lower=20000, upper=180000)
            return result
        result = [dict(row) for row in data]
        for row in result:
            row["age"] = min(85.0, max(18.0, float(row["age"])))
            row["annual_income"] = min(180000.0, max(20000.0, float(row["annual_income"])))
        return result

    @stage(pipeline, "engineer_clean_features")
    def engineer_clean_features(data: Any):
        if pd is not None and isinstance(data, pd.DataFrame):
            result = data.copy()
            min_income = float(result["annual_income"].min())
            max_income = float(result["annual_income"].max())
            span = max(max_income - min_income, 1.0)
            result["income_scaled"] = (result["annual_income"] - min_income) / span
            result["income_per_year_of_age"] = result["annual_income"] / result["age"]
            return result
        result = [dict(row) for row in data]
        incomes = [float(row["annual_income"]) for row in result]
        low, high = min(incomes), max(incomes)
        span = max(high - low, 1.0)
        for row in result:
            row["income_scaled"] = (float(row["annual_income"]) - low) / span
            row["income_per_year_of_age"] = float(row["annual_income"]) / float(row["age"])
        return result

    pipeline.add_check(
        "impute_missing_values",
        no_missing_values,
        message="Missing values remain after imputation",
        severity="error",
        code="missing_values_after_imputation",
    )
    pipeline.add_check(
        "remove_duplicate_rows",
        unique_customer_ids,
        message="Duplicate customer IDs remain after deduplication",
        severity="error",
        code="duplicate_customer_ids",
    )
    pipeline.add_check(
        "engineer_clean_features",
        lambda data: (
            bool(((data["income_scaled"] >= 0) & (data["income_scaled"] <= 1)).all())
            if pd is not None and isinstance(data, pd.DataFrame)
            else all(0.0 <= row["income_scaled"] <= 1.0 for row in data)
        ),
        message="income_scaled must remain between 0 and 1",
        severity="error",
        code="scaled_income_out_of_range",
    )

    pipeline.run(make_dataset(False), metadata={"scenario": "baseline_dirty_dataset", "synthetic": True, "backend": backend})
    pipeline.run(make_dataset(True), metadata={"scenario": "larger_dirty_dataset", "synthetic": True, "backend": backend})

    summary = _save_pipeline_artifacts(pipeline, output_root, expected_stages=4)
    print(f"  Latest run: {summary['latest_status']} | stages={summary['stage_count']} | findings={summary['finding_count']}")
    print(f"  Comparison changes: {len(summary['comparison_stage_changes'])}")
    return summary


def main() -> int:
    print("=" * 76)
    print("STAGEWATCH - THREE-PIPELINE REAL-WORLD VALIDATION")
    print("=" * 76)
    print(f"StageWatch version : {stagewatch.__version__}")
    print(f"Python             : {platform.python_version()} ({sys.executable})")
    print(f"StageWatch module  : {Path(stagewatch.__file__).resolve()}")
    print(f"NumPy              : {_version(np) or 'not installed'}")
    print(f"Pandas             : {_version(pd) or 'not installed'}")
    print(f"PyTorch            : {_version(torch) or 'not installed'}")
    print("Data source        : deterministic synthetic data generated locally")
    print(f"Output directory   : {OUTPUT_ROOT}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    jobs = [
        ("image_processing", run_image_processing),
        ("ml_inference", run_ml_inference),
        ("data_cleaning", run_data_cleaning),
    ]
    for name, job in jobs:
        try:
            results.append(job(OUTPUT_ROOT / name))
        except Exception as exc:
            failures.append({"pipeline": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"\n  ERROR in {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()

    summary = {
        "stagewatch_version": stagewatch.__version__,
        "python_version": platform.python_version(),
        "optional_backends": {
            "numpy": _version(np),
            "pandas": _version(pd),
            "torch": _version(torch),
        },
        "synthetic_data_only": True,
        "pipelines_completed": len(results),
        "pipelines_failed": len(failures),
        "results": results,
        "failures": failures,
        "output_directory": str(OUTPUT_ROOT),
    }
    _write_json(OUTPUT_ROOT / "combined_summary.json", summary)

    lines = [
        "STAGEWATCH - THREE-PIPELINE VALIDATION SUMMARY",
        "=" * 52,
        f"StageWatch: {stagewatch.__version__}",
        f"Completed:  {len(results)}/3",
        f"Failed:     {len(failures)}",
        "",
    ]
    for item in results:
        lines.extend([
            f"{item['pipeline']}: {item['latest_status']}",
            f"  stages={item['stage_count']}  findings={item['finding_count']}  history_runs={item['history_runs']}",
            f"  HTML report: {item['artifacts']['html']}",
        ])
    if failures:
        lines.extend(["", "FAILURES:"])
        lines.extend(f"- {item['pipeline']}: {item['error']}" for item in failures)
    else:
        lines.extend(["", "ALL THREE PIPELINES COMPLETED SUCCESSFULLY."])
    lines.append("Note: these are synthetic integration scenarios, not production workload benchmarks.")
    (OUTPUT_ROOT / "combined_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 76)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 76)
    for item in results:
        print(
            f"{item['pipeline']:<30} {item['latest_status']:<9} "
            f"stages={item['stage_count']} findings={item['finding_count']}"
        )
    print(f"Pipelines completed: {len(results)}/3")
    print(f"Pipelines failed   : {len(failures)}")
    print(f"Reports saved to   : {OUTPUT_ROOT}")
    print("Note: expected findings include injected/known outliers and remaining data-quality issues; wildcard shape contracts suppress permitted batch/row-count changes.")
    if failures:
        print("VALIDATION INCOMPLETE - inspect combined_summary.json and the traceback above.")
        return 1
    print("ALL THREE PIPELINE SCENARIOS COMPLETED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
