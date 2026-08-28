# 0003: Golden acceptance fixtures ship inside the installed package

## Status

Accepted (Milestone 0/1 prototype).

## Context

EarlyDesign.md section 20.3 defines six golden acceptance cases. The CLI's
`s3-ecological demo --fixture <name>` subcommand (section 23.1: "one
deterministic library entry point and one fixture-backed CLI command") needs
to run one of these cases with zero configuration, whether invoked from a
source checkout or from an installed wheel. `pytest`'s golden-fixture test
needs the identical data, not a second copy that can drift.

## Decision

Golden fixture data (`request.json`, optional `occurrences.json`,
`expected.json` per case) lives under
`src/s3_ecological/fixtures/golden/<case_name>/`, inside the installed
package, rather than under `tests/fixtures/golden/` as a test-only asset.
`pyproject.toml` declares it as package data
(`s3_ecological = ["fixtures/golden/**/*.json"]`).
`s3_ecological.fixtures.golden_loader` is the single loader used by both the
CLI (`cli.py`) and `tests/golden/test_golden_cases.py`, located via
`importlib.resources.files(...)` so it works identically from a checkout or
an installed wheel.

## Consequences

- Exactly one copy of golden fixture data; the CLI demo and the pytest
  golden-fixture test cannot silently diverge.
- The package ships slightly more data than strictly required for library
  use (acceptable at this size: six small JSON fixture sets).
