#!/usr/bin/env python3
"""Validate StageWatch release artifacts without third-party dependencies.

Run after building distributions:
    python scripts/release_preflight.py

This complements (but does not replace) `python -m twine check dist/*`.
"""
from __future__ import annotations

import argparse
import hashlib
import tarfile
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXPECTED_NAME = "stagewatch"
EXPECTED_VERSION = "0.2.0a1"
EXPECTED_OWNER = "Harish Raagav K J"
EXPECTED_REPOSITORY = "https://github.com/harishraagav/StageWatch"


def fail(message: str) -> None:
    print(f"FAIL  {message}")
    raise SystemExit(1)


def pass_check(message: str) -> None:
    print(f"PASS  {message}")


def read_wheel_metadata(path: Path):
    with ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(candidates) != 1:
            fail(f"{path.name}: expected one dist-info/METADATA, found {len(candidates)}")
        metadata = Parser().parsestr(archive.read(candidates[0]).decode("utf-8"))
        names = set(archive.namelist())
        required = {
            "stagewatch/__init__.py",
            "stagewatch/pipeline.py",
            "stagewatch/inspection.py",
            "stagewatch/py.typed",
            "stagewatch/integrations/numpy.py",
            "stagewatch/integrations/pandas.py",
            "stagewatch/integrations/torch.py",
        }
        missing = required - names
        if missing:
            fail(f"{path.name}: missing wheel files: {', '.join(sorted(missing))}")
        return metadata


def read_sdist_metadata(path: Path):
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        candidates = [name for name in names if name.endswith("/PKG-INFO") and ".egg-info/" not in name]
        if len(candidates) != 1:
            fail(f"{path.name}: expected one PKG-INFO, found {len(candidates)}")
        required_suffixes = (
            "/pyproject.toml",
            "/README.md",
            "/LICENSE",
            "/src/stagewatch/pipeline.py",
            "/tests/test_stagewatch.py",
            "/tests/test_stagewatch_020.py",
            "/docs/PUBLISHING.md",
        )
        for suffix in required_suffixes:
            if not any(name.endswith(suffix) for name in names):
                fail(f"{path.name}: missing {suffix}")
        return Parser().parsestr(archive.extractfile(candidates[0]).read().decode("utf-8"))


def validate_metadata(metadata, label: str) -> None:
    expected = {
        "Name": EXPECTED_NAME,
        "Version": EXPECTED_VERSION,
        "Author": EXPECTED_OWNER,
        "Maintainer": EXPECTED_OWNER,
        "License-Expression": "MIT",
    }
    for key, value in expected.items():
        actual = metadata.get(key)
        if actual != value:
            fail(f"{label}: {key} expected {value!r}, got {actual!r}")
    if metadata.get("Requires-Python") != ">=3.10":
        fail(f"{label}: unexpected Requires-Python: {metadata.get('Requires-Python')!r}")
    project_urls = metadata.get_all("Project-URL", [])
    url_values = {item.split(",", 1)[-1].strip() for item in project_urls if "," in item}
    if EXPECTED_REPOSITORY not in url_values:
        fail(f"{label}: repository URL missing from project metadata")
    if f"{EXPECTED_REPOSITORY}/issues" not in url_values:
        fail(f"{label}: issue tracker URL missing from project metadata")
    pass_check(f"{label}: name, version, author, maintainer, license, Python floor and project URLs")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate StageWatch 0.2.0a1 release files.")
    parser.add_argument("--verify-checksums", action="store_true", help="also verify SHA256SUMS.txt (use against the exact bundled dist/ files)")
    args = parser.parse_args()

    print("StageWatch 0.2.0a1 release artifact preflight")
    print(f"Project root: {ROOT}")
    wheels = sorted(DIST.glob("stagewatch-0.2.0a1-*.whl"))
    sdists = sorted(DIST.glob("stagewatch-0.2.0a1.tar.gz"))
    if len(wheels) != 1:
        fail(f"expected exactly one 0.2.0a1 wheel in {DIST}, found {len(wheels)}")
    if len(sdists) != 1:
        fail(f"expected exactly one 0.2.0a1 source archive in {DIST}, found {len(sdists)}")
    validate_metadata(read_wheel_metadata(wheels[0]), "Wheel metadata")
    validate_metadata(read_sdist_metadata(sdists[0]), "Source metadata")

    if args.verify_checksums:
        sums = ROOT / "SHA256SUMS.txt"
        if not sums.is_file():
            fail("--verify-checksums requested, but SHA256SUMS.txt is missing")
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                fail(f"malformed checksum line: {line!r}")
            expected_hash, relative = parts
            target = ROOT / relative.strip().lstrip("*")
            if not target.is_file():
                fail(f"checksum target missing: {relative}")
            actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                fail(f"checksum mismatch: {relative}")
        pass_check("SHA-256 manifest matches all listed distribution files")

    pass_check("release distributions have required source and package contents")
    print("\nPreflight passed. Run `python -m twine check dist/*` before upload.")
    print("This script does not check remote CI, PyPI name availability or publish artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
