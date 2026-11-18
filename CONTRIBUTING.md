# Contributing

Thanks for considering a contribution to StageWatch.

## Before opening a pull request

1. Open an issue describing the problem or proposed change.
2. Keep core runtime dependencies at zero unless there is a compelling reason.
3. Add or update tests for every behaviour change.
4. Update README/docs and CHANGELOG where appropriate.
5. Run `python run_all_tests.py`, `pytest` (when installed), and `ruff check src tests` (when installed).

## Design principles

- Local-first and offline by default.
- Never persist raw inputs or outputs by default.
- Keep optional framework integrations optional.
- Prefer stable, documented Python APIs over clever implicit behaviour.
- Treat inspection as best-effort and bounded; do not unexpectedly consume iterators or synchronize GPUs.

## Pull requests

Use focused changes, explain the motivation, include tests, and document known limitations. Do not include secrets, real customer data, large generated artifacts, or personal information in fixtures.
