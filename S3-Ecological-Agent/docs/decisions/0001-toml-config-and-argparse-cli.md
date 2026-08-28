# 0001: TOML configuration and stdlib `argparse` CLI

## Status

Accepted (Milestone 0/1 prototype).

## Context

EarlyDesign.md section 16.2 allows either YAML or TOML for versioned
configuration, and requires a CLI entry point without prescribing a
framework. The prototype must stay offline-first with a minimal dependency
footprint (only `pydantic>=2` as a hard runtime dependency).

## Decision

- **Configuration format: TOML**, parsed with the Python 3.11 standard
  library `tomllib` module. This avoids adding PyYAML as a dependency and
  keeps parsing entirely in the standard library. `config/sources.example.toml`
  and `config/thresholds.example.toml` are the documented templates.
- **CLI: stdlib `argparse`**, exposed as the `s3-ecological` console script
  (see `pyproject.toml`'s `[project.scripts]`). No click/typer dependency.
  Two subcommands: `demo --fixture <name>` (zero-configuration, runs a golden
  acceptance fixture) and `assess --input <path> --output <path|->`.

## Consequences

- Configuration precedence is: constructor/CLI overrides > environment
  variables (`S3_<FIELD_NAME>`) > TOML file(s), later files win > Profile
  v0.1 defaults hard-coded in `settings.py`. This chain is implemented once,
  in `S3Settings.load()`.
- Adding a YAML config loader later (if a downstream integrator needs it) is
  additive: a second `S3Settings.load_yaml(...)` classmethod could be added
  without touching the TOML path.
