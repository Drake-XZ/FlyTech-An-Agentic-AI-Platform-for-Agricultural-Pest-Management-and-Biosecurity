"""Torch-gated offline smoke test and fixed-seed reproducibility test for
``scripts/train_geo_prior.py`` (DesignSuggestionLog.md "2026-09-09 ...
Suggested next increment: M2-C geographic-prior reproduction and locked
spatial evaluation").

Skipped entirely under the main venv (no torch dependency there - see
``pyproject.toml``). Run for real via (from the repo root):

    data/local/m2/s1/venv/Scripts/python.exe -m pytest \
        tests/integration/test_geo_prior_training.py -q

Uses a tiny synthetic CSV fixture, never the real M2 data, and forces CPU
(``--force-cpu``) so the determinism assertion is not dependent on whatever
GPU (if any) happens to be present - CUDA's CuBLAS kernels are documented by
PyTorch as not bit-exact reproducible even with
``torch.use_deterministic_algorithms(True)``, while CPU execution is. The
real, full 200-epoch/patience-40 training run recorded in ``WorkLog.md`` used
CUDA for speed; this test's CPU-only determinism guarantee is a property of
the training procedure and its seeding, not a claim that the GPU-trained
checkpoint used for M2-C evaluation is itself bit-reproducible run-to-run.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


train_geo_prior = _load_module("train_geo_prior")

CSV_FIELDS = [
    "source",
    "source_record_id",
    "taxon_id",
    "genus",
    "latitude",
    "longitude",
    "event_date",
]


def _row(record_id: str, genus: str, latitude: float, longitude: float, event_date: str) -> dict:
    return {
        "source": "test",
        "source_record_id": record_id,
        "taxon_id": f"t:{genus}",
        "genus": genus,
        "latitude": str(latitude),
        "longitude": str(longitude),
        "event_date": event_date,
    }


# 3 records per genus, spread over distinct locations; two records carry no
# usable event_date (one empty, one year-only) so the date-aware config's
# filtering path is exercised without crashing, mirroring the real data's
# partial-precision dates.
_FIXTURE_ROWS = [
    _row("a1", "Anastrepha", 10.0, 20.0, "2020-01-15"),
    _row("a2", "Anastrepha", 11.0, 21.0, "2020-06-15"),
    _row("a3", "Anastrepha", 12.0, 22.0, ""),
    _row("b1", "Bactrocera", -10.0, -20.0, "2020-02-15"),
    _row("b2", "Bactrocera", -11.0, -21.0, "2020-07-15"),
    _row("b3", "Bactrocera", -12.0, -22.0, "2013"),
    _row("c1", "Ceratitis", 30.0, 40.0, "2020-03-15"),
    _row("c2", "Ceratitis", 31.0, 41.0, "2020-08-15"),
    _row("c3", "Ceratitis", 32.0, 42.0, "2020-09-15"),
    _row("d1", "Rhagoletis", -30.0, -40.0, "2020-04-15"),
    _row("d2", "Rhagoletis", -31.0, -41.0, "2020-10-15"),
    _row("d3", "Rhagoletis", -32.0, -42.0, "2020-11-15"),
]

_FIXTURE_VALIDATION_ROWS = [
    _row("va1", "Anastrepha", 10.5, 20.5, "2020-01-20"),
    _row("vb1", "Bactrocera", -10.5, -20.5, "2020-02-20"),
    _row("vc1", "Ceratitis", 30.5, 40.5, "2020-03-20"),
    _row("vd1", "Rhagoletis", -30.5, -40.5, "2020-04-20"),
]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _make_args(tmp_path: Path, *, output_dir: Path) -> argparse.Namespace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    train_manifest = tmp_path / "train_manifest.csv"
    validation_manifest = tmp_path / "validation_manifest.csv"
    _write_csv(train_manifest, _FIXTURE_ROWS)
    _write_csv(validation_manifest, _FIXTURE_VALIDATION_ROWS)
    return argparse.Namespace(
        train_manifest=train_manifest,
        validation_manifest=validation_manifest,
        dataset_report=tmp_path / "dataset_report.json",
        output_dir=output_dir,
        seed=42,
        batch_size=4,
        epochs=2,
        patience=2,
        max_per_class=4,
        learning_rate=5e-4,
        lr_decay=0.98,
        force_cpu=True,
    )


def test_offline_cpu_smoke_completes_with_finite_loss(tmp_path):
    args = _make_args(tmp_path, output_dir=tmp_path / "training")
    selected_configuration = train_geo_prior.train(args)

    assert selected_configuration["frozen_config_id"] in {
        train_geo_prior._config_id(config) for config in train_geo_prior.CONFIG_GRID
    }
    candidate_table_path = args.output_dir / "candidate_table.json"
    assert candidate_table_path.exists()
    import json

    candidate_table = json.loads(candidate_table_path.read_text(encoding="utf-8"))
    assert candidate_table["environment"]["device"] == "cpu"
    for candidate in candidate_table["candidates"]:
        assert candidate["epochs_run"] >= 1
        for row in candidate["history"]:
            assert math.isfinite(row["train_loss"])
            assert 0.0 <= row["validation_accuracy"] <= 1.0
            assert 0.0 <= row["validation_macro_f1"] <= 1.0


def test_fixed_seed_training_is_deterministic_on_cpu(tmp_path):
    args_first = _make_args(tmp_path / "run1", output_dir=tmp_path / "run1" / "training")
    args_second = _make_args(tmp_path / "run2", output_dir=tmp_path / "run2" / "training")

    selected_first = train_geo_prior.train(args_first)
    selected_second = train_geo_prior.train(args_second)

    assert selected_first["frozen_config_id"] == selected_second["frozen_config_id"]
    assert selected_first["checkpoint_sha256"] == selected_second["checkpoint_sha256"]
