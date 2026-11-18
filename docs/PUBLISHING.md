# Publishing StageWatch 0.2.0a1

## Release ownership

StageWatch is authored, developed and maintained solely by **Harish Raagav K J**. The package metadata, README, citation file and MIT copyright notice use that attribution.

## Verified repository and CI state

- Canonical repository: https://github.com/harishraagav/StageWatch
- Release branch: main
- The GitHub Actions run for commit a70261063c0f2359d6b09581ab20dfc7d53cd2c4 completed **16/16 jobs successfully**. It covered Ubuntu, Windows and macOS with Python 3.10–3.14, Ruff, builds, artifact preflight, Twine validation and a separate PyTorch integration job.
- The maintainer reports that the PyPI Trusted Publisher has been configured for this repository. Confirm that its project, workflow and environment match the values below before publishing.

## PyPI Trusted Publishing configuration

| Setting | Value |
|---|---|
| PyPI project | stagewatch |
| Owner | harishraagav |
| Repository | StageWatch |
| Workflow filename | publish.yml |
| GitHub environment | pypi |

The workflow at .github/workflows/publish.yml runs when a GitHub Release is published. It builds the wheel and source distribution from the release tag, then publishes using GitHub OIDC via PyPI Trusted Publishing. No PyPI API token is required.

## Release version

The first public alpha pre-release is **0.2.0a1**, with Git tag **v0.2.0a1**. Keep pyproject.toml, src/stagewatch/__init__.py, CITATION.cff, CHANGELOG.md and RELEASE_NOTES.md aligned.

## Create the GitHub prerelease

1. Open https://github.com/harishraagav/StageWatch/releases/new.
2. Choose **Create a new tag** and enter v0.2.0a1.
3. Set the target to main.
4. Set the release title to StageWatch 0.2.0a1.
5. Use the contents of RELEASE_NOTES.md as the release description.
6. Check **Set as a pre-release**.
7. Publish the release.

Publishing the GitHub Release triggers .github/workflows/publish.yml. Monitor the Actions run. A successful workflow should create the PyPI release at https://pypi.org/project/stagewatch/.

## Verify after publication

Use a clean virtual environment and explicitly allow pre-releases:

    python -m pip install --upgrade pip
    python -m pip install --pre stagewatch
    python -c "import stagewatch; print(stagewatch.__version__)"
    python -m pip show stagewatch

The imported version must be 0.2.0a1. Optional integrations can be installed with:
- python -m pip install --pre "stagewatch[numpy]"
- python -m pip install --pre "stagewatch[pandas]"
- python -m pip install --pre "stagewatch[torch]"
- python -m pip install --pre "stagewatch[all]"

## Local release checks

From the repository root:

    python -m pip install -e ".[dev,numpy,pandas,torch]"
    python run_all_tests.py
    python run_three_pipeline_validation.py
    python -m build
    python scripts/release_preflight.py
    python -m twine check dist/*

Do not publish if the built wheel or source archive differs from version 0.2.0a1. Do not upload stale 0.2.0 artifacts.

## Security notes

Do not commit PyPI tokens, passwords, recovery codes or other credentials. Trusted Publishing uses an OIDC identity token issued to the GitHub Actions job.
