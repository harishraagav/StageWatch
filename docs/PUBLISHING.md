# Publishing StageWatch 0.2.0

## Release ownership

StageWatch is authored, developed and maintained by **Harish Raagav K J**. The
package metadata, README, citation file and MIT copyright notice use that
attribution. No author email address is included because one has not been
provided.

## Current release state

The 0.2.0 source bundle and distributions are prepared and have passed the
maintainer's reported Windows validation: 57 tests, zero failures, zero errors
and zero skips with NumPy, Pandas and PyTorch installed. Three additional
pipeline scenarios completed. This does not replace the remote GitHub Actions
CI matrix or a final test immediately before upload.

The normalized PyPI project endpoints were checked on 2026-11-18 and returned
HTTP 404 at the time of the check:

- https://pypi.org/project/stagewatch/
- https://pypi.org/pypi/stagewatch/json

This suggests no project was registered under that name at check time. PyPI
project names are first-come, first-served; repeat the check immediately before
creating the project or publishing. A 404 is not a name reservation.

## Canonical GitHub repository

The maintainer has supplied the canonical repository:

- Repository: https://github.com/harishraagav/StageWatch
- Issues: https://github.com/harishraagav/StageWatch/issues
- Test workflow: https://github.com/harishraagav/StageWatch/actions/workflows/tests.yml
- Publish workflow: `.github/workflows/publish.yml`

The repository URL is recorded in `pyproject.toml`, `README.md` and
`CITATION.cff`. The release owner must ensure the repository is public and that
its default branch contains this exact release source before creating `v0.2.0`.

## Remaining publication steps

1. Confirm the `stagewatch` name is still available on PyPI immediately before
   configuring the publisher. A prior 404 check is not a reservation.
2. Configure PyPI Trusted Publishing for owner `harishraagav`, repository
   `StageWatch`, workflow file `.github/workflows/publish.yml`, and GitHub
   environment `pypi`. If the PyPI project has not yet been created, add the
   publisher as a pending publisher on PyPI.
3. Push this source to the `main` branch and wait for the full GitHub Actions test
   matrix to pass.
4. Create and publish a GitHub release tagged `v0.2.0`. The publish workflow
   builds the distributions and uploads them using GitHub OIDC; no PyPI API
   token is needed when Trusted Publishing is configured correctly.

## Connect the local release source to GitHub

If the GitHub repository is empty, from the extracted project root run:

```bash
git init -b main
git add .
git commit -m "Prepare StageWatch 0.2.0 release"
git remote add origin https://github.com/harishraagav/StageWatch.git
git push -u origin main
```

If the repository already contains commits or files, clone it first and merge
this release source into that working tree instead of force-pushing. Review the
existing README, license, workflows and branch protections before resolving any
conflicts. Do not use `git push --force` to overwrite the repository.

## Local release checks

Run these from the project root in a clean environment:

```bash
python -m pip install -e ".[dev,numpy,pandas,torch]"
python run_all_tests.py
python run_three_pipeline_validation.py
python -m build
python scripts/release_preflight.py
python -m twine check dist/*
```

The optional integration dependencies can be installed separately if a given
platform does not have compatible wheels for all extras. The test runner skips
optional integration tests only when the corresponding dependency is absent.

## Publish flow

The recommended path is GitHub Actions with PyPI Trusted Publishing. The
workflow in `.github/workflows/publish.yml` runs on a published GitHub release,
builds wheel and source archive, then invokes the official PyPI publishing
action with an OIDC identity token. Configure the same repository, workflow
filename and environment name in PyPI's Trusted Publisher settings.

Do not commit PyPI tokens, passwords, recovery codes or other credentials.
Do not put credentials in the repository, workflow file or issue tracker.

## Manual fallback (only if Trusted Publishing cannot be used)

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Use a narrowly scoped PyPI API token and enter it interactively when Twine asks.
Never store the token in source control or in this ZIP.
