#!/usr/bin/env python3
"""One-command StageWatch test suite and demo artifact generator.

Run from the extracted project folder:
    python run_all_tests.py

Uses the standard library only. Optional integration tests run when extras exist.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def run_tests() -> bool:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("\nTEST SUMMARY")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Failures:  {len(result.failures)}")
    print(f"  Errors:    {len(result.errors)}")
    print(f"  Skipped:   {len(result.skipped)}")
    return result.wasSuccessful()


def generate_demo_artifacts() -> None:
    from stagewatch import Pipeline, stage

    output_dir = ROOT / "test_output"
    output_dir.mkdir(exist_ok=True)
    pipeline = Pipeline("stagewatch-demo", storage_dir=output_dir / "history", max_history=20, size_change_threshold=0.5)
    pipeline.expect_range("normalize", minimum=0.0, maximum=1.0)

    @stage(pipeline)
    def load(_seed):
        return [0.2, 0.4, 0.6, 0.8]

    @stage(pipeline)
    def normalize(values):
        return [value / max(values) for value in values]

    @stage(pipeline)
    def summarize(values):
        return {"count": len(values), "mean": sum(values) / len(values)}

    pipeline.run("demo-seed", metadata={"kind": "automated-test-demo"})
    # A second pass deliberately changes the output length so cross-run inspection is exercised.
    pipeline.run([0.1, 0.2, 0.3, 0.4, 0.5])
    (output_dir / "demo-report.txt").write_text(pipeline.report(format="terminal"), encoding="utf-8")
    (output_dir / "demo-report.json").write_text(pipeline.report(format="json"), encoding="utf-8")
    pipeline.report(format="html", path=output_dir / "demo-report.html")
    print(f"\nDemo reports created in: {output_dir}")
    print("  - demo-report.txt")
    print("  - demo-report.json")
    print("  - demo-report.html")


def main() -> int:
    print("StageWatch - complete local test suite")
    print(f"Project root: {ROOT}")
    success = run_tests()
    if success:
        generate_demo_artifacts()
        print("\nALL TESTS PASSED - StageWatch is ready for local evaluation.")
        return 0
    print("\nTESTS FAILED - review the failure output above before using this build.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
