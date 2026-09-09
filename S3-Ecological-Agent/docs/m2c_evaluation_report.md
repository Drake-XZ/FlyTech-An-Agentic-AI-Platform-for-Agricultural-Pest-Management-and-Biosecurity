# M2-C evaluation report — geographic-prior reproduction and locked spatial test

**Status:** experimental research result. Not a production-readiness claim and not a biosecurity or biological-efficacy claim. Reports S1-only, geographic-only, and fixed-fusion performance separately on a single locked spatial `test` evaluation.

## Reproduction method

The `geo_prior` (Mac Aodha, Cole & Perona) presence-only geographic prior was reproduced under `scripts/geo_prior_model.py` (self-contained, unmodified from `research/third_party/geo_prior/` at commit `257dc7e30f3cc6bf02fbec55ee878724d077fe61` in architecture/loss/encoding, adapted only to this repository's data adapter). It was fit **exclusively** on the spatial `train` split (`spatial_split_identity` `59014aec1786e0cb7d4c2d9db0a091fa8c0a7a797c918185516d41d81f670183`), using a predeclared 2x2 configuration grid (`num_filts in {64, 256}` x `use_date_feats in {False, True}`), with the single winning configuration selected **exclusively** on the spatial `validation` split's genus macro-F1. No `test`-split label or coordinate was read, viewed, or used at any point before the configuration and checkpoint hash were frozen in `data/local/m2/geo_prior/training/selected_configuration.json`.

Full architecture, config-grid results, and reproduction assumptions/limitations (no user-identity loss term, date-feature exclusion counts, `geo_support`-as-raw-sigmoid mapping, GPU/CPU determinism scope) are in `docs/model_cards/geo_prior_baseline_v0.1.md`; this report covers only the validation selection result and the one locked test run.

## Validation-set selection result

| config_id | num_filts | use_date_feats | best_epoch | validation accuracy | validation macro-F1 |
| --- | --- | --- | --- | --- | --- |
| `filts64_dateFalse` | 64 | false | 101 | 88.74% | 77.94% |
| `filts64_dateTrue` | 64 | true | 171 | 85.94% | 70.43% |
| `filts256_dateFalse` | 256 | false | 65 | 89.36% | 80.10% |
| **`filts256_dateTrue`** | **256** | **true** | **65** | **90.54%** | **80.41%** |

Winner: `filts256_dateTrue`, selected by highest validation macro-F1 (no tie-break needed).

## Frozen configuration

- `frozen_config_id`: `filts256_dateTrue` (`num_filts=256, use_date_feats=true`).
- `checkpoint_sha256`: `952d81008184f18888d22de54b3557f7c5429b35ed28782aabd6914707e61086`.
- `train_manifest_sha256`: `606ca93ce1b6a0f66922d7f6ec556abb4256db31b109f362a4354da7249fb0c1` (11,403 date-usable train records).
- `validation_manifest_sha256`: `5eaf6c96162fbb5e987b37f7c7a9871ce570a3c645a40dc0fefeeac0230bac5f` (3,215 date-usable validation records).
- `spatial_split_identity`: `59014aec1786e0cb7d4c2d9db0a091fa8c0a7a797c918185516d41d81f670183`.

## Locked spatial-test evaluation

Run exactly once, via `scripts/evaluate_geo_prior_m2c.py`, on the validated temporary S1 bundle's 942 spatial-test observations (`s1_bundle_manifest_sha256` `017014a2fe218249739908130d93343ca0b16c8100120eba2c1a4088332ad289`). The S1 bundle was re-validated against the current `spatial_split_identity` before use. The fixed-fusion formula and Prototype Implementation Profile v0.1 constants (`fusion_epsilon=1e-6`, `fusion_weight_geo=1.0`, `fusion_weight_environment=0.0`) were used unmodified from `src/s3_ecological/fusion/soft_fusion.py` and `S3Settings` — none was tuned, calibrated, or learned from validation or test data.

Bootstrap 95% confidence intervals: fixed seed 42, 2,000 observation-level resamples with replacement.

### S1-only (visual baseline)

942 observations. Accuracy 89.92% (95% CI 87.90%–91.93%); macro-F1 79.27% (95% CI 74.90%–83.55%).

| Genus | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| Anastrepha | 31 | 44.12% | 48.39% | 46.15% |
| Bactrocera | 165 | 77.66% | 92.73% | 84.53% |
| Ceratitis | 371 | 95.26% | 92.18% | 93.70% |
| Rhagoletis | 375 | 95.74% | 89.87% | 92.71% |

Confusion matrix (rows = true, columns = predicted; order Anastrepha/Bactrocera/Ceratitis/Rhagoletis):

```
              Anastrepha  Bactrocera  Ceratitis  Rhagoletis
Anastrepha            15          15          1           0
Bactrocera             1         153          6           5
Ceratitis              6          13        342          10
Rhagoletis            12          16         10         337
```

### Geo-only (geographic prior)

927 of 942 observations (15 excluded: the frozen configuration is date-aware and these observations have no fully usable `observed_at`). Accuracy 89.97% (95% CI 88.03%–91.80%); macro-F1 87.82% (95% CI 84.64%–90.59%).

| Genus | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| Anastrepha | 30 | 80.56% | 96.67% | 87.88% |
| Bactrocera | 159 | 100.00% | 66.04% | 79.55% |
| Ceratitis | 367 | 83.94% | 94.01% | 88.69% |
| Rhagoletis | 371 | 94.67% | 95.69% | 95.17% |

Confusion matrix (same genus order, 927-observation scope):

```
              Anastrepha  Bactrocera  Ceratitis  Rhagoletis
Anastrepha            29           0          1           0
Bactrocera             0         105         50           4
Ceratitis              6           0        345          16
Rhagoletis             1           0         15         355
```

### Fixed fusion (S1 + geo, unmodified `soft_fusion.fuse`)

942 observations (the 15 date-missing observations still fuse, since the fusion formula only omits the `geo_support` term when it is `None`; their prediction is visual-only in effect). Accuracy 95.01% (95% CI 93.63%–96.39%); macro-F1 92.52% (95% CI 89.74%–95.03%).

| Genus | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| Anastrepha | 31 | 80.00% | 90.32% | 84.85% |
| Bactrocera | 165 | 92.35% | 95.15% | 93.73% |
| Ceratitis | 371 | 94.92% | 95.69% | 95.30% |
| Rhagoletis | 375 | 97.80% | 94.67% | 96.21% |

Confusion matrix (942-observation scope):

```
              Anastrepha  Bactrocera  Ceratitis  Rhagoletis
Anastrepha            28           3          0           0
Bactrocera             0         157          7           1
Ceratitis              3           6        355           7
Rhagoletis             4           4         12         355
```

## Summary

| Method | Observations | Accuracy | Macro-F1 |
| --- | --- | --- | --- |
| S1-only | 942 | 89.92% | 79.27% |
| Geo-only | 927 | 89.97% | 87.82% |
| Fixed fusion | 942 | **95.01%** | **92.52%** |

Fixed fusion improved over S1-only on this single locked test, most visibly on the small Anastrepha class (F1 46.15% -> 84.85%). This is a one-off experimental measurement on 942 (or 927) observations, not a statistically definitive or production claim.

## Limitations

- **Small Anastrepha support** (31 of 942 test observations, 30 of 927 for geo-only): its per-genus metrics are high-variance; treat every confusion-matrix Anastrepha row and its bootstrap interval with caution.
- **iNaturalist research-grade ground truth**, not expert-verified biosecurity identification.
- **Closed four-genus classifier**: S1 is a closed-set softmax with no unknown-taxon class; the geographic prior likewise only distinguishes among these four genera.
- **Global, label-only geographic scope**: the geographic prior uses only location (and, for the frozen config, date) — no environmental or seasonal-range covariates.
- **Single locked run**: this evaluation was executed exactly once against the frozen configuration and the already-validated S1 bundle; no test-set metric influenced model selection or the fusion formula.
- No Prototype Implementation Profile v0.1 threshold, fusion weight, risk-state precedence rule, public schema, or S3 runtime behaviour was changed to produce this result.
