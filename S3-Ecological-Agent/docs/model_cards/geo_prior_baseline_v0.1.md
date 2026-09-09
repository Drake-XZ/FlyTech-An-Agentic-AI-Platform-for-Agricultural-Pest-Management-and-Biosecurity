# Geographic-prior baseline v0.1 — M2-C reproduction

## Purpose and status

`flytech-reproduced-geo-prior-fcnet-v0.1` is an **isolated research reproduction** of the presence-only geographic prior described by Mac Aodha, Cole & Perona, fitted on the FlyTech S3 Milestone 2 spatial `train` split and selected on `validation` only. It supplies the `geo_support` term used by M2-C's locked fixed-fusion evaluation. It is not part of the S3 runtime, does not change `src/s3_ecological/fusion/` weights or Prototype Implementation Profile v0.1 thresholds, and is not the original authors' checkpoint — no pretrained weight is published upstream.

## Provenance

- Upstream repository: `https://github.com/macaodha/geo_prior`, vendored unmodified at `research/third_party/geo_prior/`, commit `257dc7e30f3cc6bf02fbec55ee878724d077fe61`. No licence file and no released pretrained weight (confirmed 404).
- Reproduction lives entirely under `scripts/geo_prior_model.py` (self-contained: `FCNet`, `encode_loc_time`, non-user `embedding_loss`) and is never imported by `src/s3_ecological`.
- Training data: the authorised M2 occurrence snapshot (`occurrence_snapshot_sha256` `28f6f59dc8444885e65ebd70009f5f05d5d4dca99875d06896b7b5c168d48112`) joined against the spatial split manifest (`spatial_split_manifest_sha256` `336408a8d3dc2553961bae51735dd78138a8ad399cd5a863d46c027c9b305dc6`, `spatial_split_identity` `59014aec1786e0cb7d4c2d9db0a091fa8c0a7a797c918185516d41d81f670183`) and the taxonomy snapshot (`taxonomy_snapshot_sha256` `3e9e1ab4cae81476f68fa9c829aa97c5c8bba53e07348135d90f85e0f4eb5851`).

## Reproduction assumptions and hard limitations

- **No user/recorder-ID term.** `RawOccurrenceRecord` has no recorder-identity field, so the paper's default training loss (which includes a per-observer term) cannot be reproduced. This reproduction uses `embedding_loss`'s non-user `full_loss` variant only — a hard data limitation, not a style choice.
- **`geo_support` mapping.** Each candidate's `geo_support` is the model's raw per-genus `sigmoid(class_emb(loc_emb))` output, used directly with no cross-genus normalisation — consistent with this codebase's existing `geo_support` semantics (an independent per-candidate score in `(0, 1]`, never a cross-candidate distribution; absent evidence is `None`, never a substituted zero).
- **Date-feature exclusion.** Roughly half of usable M2 occurrences have no `event_date`, and a further subset carries an unusable partial date (e.g. year-only, mirroring the fixture case exercised by `tests/integration/test_geo_prior_training.py`). A date-aware configuration trains and is selected only on records with a fully usable date: this excluded 33 of 11,436 train records and 27 of 3,242 validation records (the plain "no `event_date` at all" counts are smaller — 4 train / 9 validation — the remainder are non-empty but partial/unparseable dates). The winning configuration's reported `train_count=11,403` / `validation_count=3,215` are exactly `11,436-33` / `3,242-27`. No invented midnight timestamp is ever substituted for a missing or unusable date, matching the S1 card's own convention.
- **Training-schedule departure.** `batch_size=64`, `num_epochs<=200` with early-stop patience 40 was used instead of the paper's `batch_size=1024, num_epochs=30` — a documented departure justified by the much smaller (~11k-record, 4-class) dataset here versus iNaturalist-scale data.
- **GPU non-determinism.** The real training run below used CUDA (`torch.device("cuda")`) for speed; PyTorch documents that CuBLAS kernels are not bit-exact reproducible even under `torch.use_deterministic_algorithms(True)`. The fixed-seed reproducibility guarantee actually tested (`tests/integration/test_geo_prior_training.py`) is scoped to CPU execution (`--force-cpu`): it proves the training *procedure and seeding* are deterministic, not that this specific GPU-trained checkpoint is bit-reproducible run-to-run.

## Method

`FCNet`: `Linear(num_inputs, num_filts) -> ReLU -> 4x ResLayer -> class_emb Linear(num_filts, num_classes, bias=False)`, output `sigmoid(class_emb(loc_emb))`. Location encoding is `encode_cos_sin`: `[sin(pi*lon/180), sin(pi*lat/90), cos(pi*lon/180), cos(pi*lat/90)]`, plus `[sin(pi*date), cos(pi*date)]` when date features are enabled. Optimiser: Adam, `lr=5e-4`, `lr_decay=0.98`/epoch, class-balanced sampler (`max_num_exs_per_class=100`, resampled each epoch), seed 42.

Config grid (train-only fit, validation-only selection; 2x2 = 4 candidates): `num_filts in {64, 256}` x `use_date_feats in {False, True}`.

| config_id | num_filts | use_date_feats | best_epoch | validation accuracy | validation macro-F1 |
| --- | --- | --- | --- | --- | --- |
| `filts64_dateFalse` | 64 | false | 101 | 88.74% | 77.94% |
| `filts64_dateTrue` | 64 | true | 171 | 85.94% | 70.43% |
| `filts256_dateFalse` | 256 | false | 65 | 89.36% | 80.10% |
| **`filts256_dateTrue`** | **256** | **true** | **65** | **90.54%** | **80.41%** |

Selection rule (applied to validation-only genus macro-F1): highest `best_validation_macro_f1`, ties broken by smaller `num_filts`, then by preferring `use_date_feats=False`. **`filts256_dateTrue` won outright** — no tie-break was needed.

## Frozen configuration

- `frozen_config_id`: `filts256_dateTrue` (`num_filts=256, use_date_feats=true`).
- `checkpoint_sha256`: `952d81008184f18888d22de54b3557f7c5429b35ed28782aabd6914707e61086`.
- `train_manifest_sha256`: `606ca93ce1b6a0f66922d7f6ec556abb4256db31b109f362a4354da7249fb0c1` (11,403 date-usable train records; 11,436 total train records before the date-aware filter excluded 33).
- `validation_manifest_sha256`: `5eaf6c96162fbb5e987b37f7c7a9871ce570a3c645a40dc0fefeeac0230bac5f` (3,215 date-usable validation records; 3,242 total before the date-aware filter excluded 27).
- `best_epoch`: 65; `best_validation_accuracy`: 90.54%; `best_validation_macro_f1`: 80.41%.
- Selection and freezing happened strictly before any test-set inference; the frozen config and checkpoint hash were written to `selected_configuration.json` prior to running `scripts/evaluate_geo_prior_m2c.py`.

## Training environment

`device=cuda`, `gpu_name=NVIDIA GeForce RTX 4060 Laptop GPU`, `torch=2.8.0+cu128`, `numpy=2.5.2`, `seed=42`.

## Reproduction

From `S3-Ecological-Agent`, with the authorised local M2 resources present:

```powershell
python scripts/prepare_geo_prior_dataset.py
data/local/m2/s1/venv/Scripts/python.exe scripts/train_geo_prior.py
data/local/m2/s1/venv/Scripts/python.exe scripts/evaluate_geo_prior_m2c.py
```

All input snapshots, per-config checkpoints, the candidate table, the frozen configuration, and the locked evaluation report remain under gitignored `data/local/`. Only the scripts, this card, and the M2-C evaluation report (`docs/m2c_evaluation_report.md`) are committed.

## Locked test use and limitations

The frozen checkpoint's `geo_support` output was used exactly once, on the validated S1 bundle's 942-observation locked spatial test scope, to compute geographic-only and fixed-fusion metrics — see `docs/m2c_evaluation_report.md` for the full result. It shares the S1 baseline's limitations: iNaturalist research-grade ground truth (not expert-verified), a small imbalanced Anastrepha subset, and a global, label-only geographic scope (no environmental or seasonal-range covariates beyond location/date encoding). This card and its evaluation are experimental reproduction results, not a production-readiness or biosecurity/biological-efficacy claim.

## M2-D robustness notes (append-only, no change to the above)

This exact frozen recipe (`filts256_dateTrue`, unchanged hyperparameters) was independently retrained — never the checkpoint above, always a fresh fit restricted to each new partition's own train split — on four additional pre-declared spatial partitions (grid sizes 0.5°/1.0°/2.0°, seeds 7/42/123), plus one no-retrain location-only ablation (`filts256_dateFalse`, M2-C's own already-trained candidate, reused read-only) on this card's own reference partition. Fixed fusion outperformed both S1-only and Geo-only on every one of the five partitions tested; Geo-only's own standalone accuracy/macro-F1 varied more across partitions (81.86%-91.50% accuracy) than S1-only's or fusion's did. Full per-partition results, the ablation comparison, and explicit statements of what this audit does not establish (no OOD/calibration/incursion claim, no new best-config selection) are in `docs/m2d_robustness_report.md`. This card's own frozen configuration, checkpoint, and locked test result above are unchanged.
