# M2-D robustness report — geographic-prior robustness, ablation, and generalisation audit

**Status:** experimental research result. Not a production-readiness claim, not a biosecurity or biological-efficacy claim, and not an open-set/OOD/calibration claim. Reports S1-only, geographic-only, and fixed-fusion performance on four new pre-declared spatial partitions plus one no-retrain ablation on the reference partition. **This report does not replace, re-tune, or supersede M2-C's locked result** (`docs/m2c_evaluation_report.md`); it is an independently labelled robustness study over the same reproduction method.

## Pre-declared matrix (frozen before any new test-set inference)

The full matrix — grid scales, split seeds, the frozen training recipe, the ablation spec, the bootstrap protocol, and the exact per-partition command template — was written to `config/m2d_robustness_matrix.json` (and the frozen M2-C reference constants to `src/s3_ecological/experiments/m2c_reference.py`) **before** any new spatial-split manifest, training run, S1 bundle, or evaluation for M2-D was produced. `tests/unit/test_m2d_matrix.py` asserts the matrix covers >= 3 grid sizes (including {0.5, 1.0, 2.0}) and >= 3 seeds (including {7, 42, 123}), and that each declared partition's spatial-split identity is deterministically reproducible and distinct from every other partition's — using the real `spatial_split.compute_split_identity` function, not a hand-computed value.

| partition_id | grid_size_degrees | seed | role |
| --- | --- | --- | --- |
| `reference` | 1.0 | 42 | M2-C's own locked spatial-test evaluation — frozen, read-only, never rerun |
| `grid0_5_seed42` | 0.5 | 42 | new training + new S1 bundle |
| `grid2_0_seed42` | 2.0 | 42 | new training + new S1 bundle |
| `grid1_0_seed7` | 1.0 | 7 | new training + new S1 bundle |
| `grid1_0_seed123` | 1.0 | 123 | new training + new S1 bundle |

Grid scales covered: {0.5, 1.0, 2.0} degrees. Seeds covered: {7, 42, 123}. Every new partition trained **only** the single frozen recipe (`filts256_dateTrue`: `num_filts=256, use_date_feats=true`, learning rate 5e-4, lr_decay 0.98, batch size 64, up to 200 epochs, patience 40, training seed 42) via `scripts/train_geo_prior.py --only-config-id filts256_dateTrue` — no hyperparameter search was repeated for any new partition. Each new partition regenerated its own S1 evaluation bundle from the shared, fixed TF4 visual checkpoint (never retrained), scoped to that partition's own spatial-test observations; `validate_s1_evaluation_bundle` structurally rejects a bundle whose `spatial_split_identity` does not match the partition being evaluated (`tests/unit/test_s1_bundle.py` covers this rejection directly). Fixed fusion formula and Prototype Implementation Profile v0.1 constants (`fusion_epsilon=1e-6`, `fusion_weight_geo=1.0`, `fusion_weight_environment=0.0`) were used unmodified in every run. Bootstrap 95% confidence intervals: fixed seed 42, 2,000 observation-level resamples (same protocol as M2-C).

All five runs below (the four new partitions plus the reference-partition ablation) are reported regardless of outcome — none were selected after the fact.

## Per-partition results

| partition_id | spatial_split_identity (prefix) | train / validation / test support | checkpoint sha256 (prefix) |
| --- | --- | --- | --- |
| `reference` (M2-C, frozen) | `59014aec1786e0cb` | 11,403 / 3,215 / 942 | `952d81008184f188` |
| `grid0_5_seed42` | `0112d9ca1477cf30` | 12,624 / 3,320 / 2,765 | `9829fbd06188bf0e` |
| `grid2_0_seed42` | `1e03e468d76b029a` | 9,382 / 6,275 / 3,052 | `03db5c10d8cc505e` |
| `grid1_0_seed7` | `510f6178417ad832` | 12,986 / 3,030 / 2,693 | `c52d0988e5b25182` |
| `grid1_0_seed123` | `20933c2f80fdc368` | 13,000 / 2,800 / 2,909 | `45bd9247eb65b308` |

(Train/validation counts above are the raw split sizes before the date-aware config's undated-record exclusion; see `geo_only` observation counts below for the post-exclusion test-time figures.)

### `grid0_5_seed42` (grid 0.5°, seed 42)

| Method | Observations | Accuracy (95% CI) | Macro-F1 (95% CI) |
| --- | --- | --- | --- |
| S1-only | 1,006 | 91.75% (90.06%–93.34%) | 85.46% (81.37%–88.89%) |
| Geo-only | 981 | 81.86% (79.41%–84.20%) | 77.72% (73.80%–81.12%) |
| Fixed fusion | 1,006 | **95.53%** (94.23%–96.72%) | **94.04%** (91.19%–96.21%) |

Geo-only excluded 25 of 1,006 test observations (missing/unusable `observed_at`). Per-genus F1 (fusion): Anastrepha 89.29% (support 28), Bactrocera 94.48% (267), Ceratitis 95.55% (371), Rhagoletis 96.85% (340).

### `grid2_0_seed42` (grid 2.0°, seed 42)

| Method | Observations | Accuracy (95% CI) | Macro-F1 (95% CI) |
| --- | --- | --- | --- |
| S1-only | 1,002 | 90.82% (89.02%–92.42%) | 81.82% (77.08%–86.02%) |
| Geo-only | 988 | 91.50% (89.68%–93.12%) | 88.68% (84.81%–91.68%) |
| Fixed fusion | 1,002 | **96.41%** (95.21%–97.60%) | **94.82%** (91.39%–97.28%) |

Geo-only excluded 14 of 1,002. Per-genus F1 (fusion): Anastrepha 91.43% (support 18), Bactrocera 96.39% (289), Ceratitis 93.88% (186), Rhagoletis 97.59% (509).

### `grid1_0_seed7` (grid 1.0°, seed 7 — same grid as reference, different split seed)

| Method | Observations | Accuracy (95% CI) | Macro-F1 (95% CI) |
| --- | --- | --- | --- |
| S1-only | 1,005 | 89.85% (87.96%–91.64%) | 80.77% (76.32%–84.51%) |
| Geo-only | 982 | 89.10% (87.07%–91.04%) | 81.98% (77.02%–86.29%) |
| Fixed fusion | 1,005 | **95.42%** (94.03%–96.72%) | **92.03%** (88.20%–94.95%) |

Geo-only excluded 23 of 1,005. Per-genus F1 (fusion): Anastrepha 80.85% (support 21), Bactrocera 95.60% (245), Ceratitis 95.87% (373), Rhagoletis 95.79% (366).

### `grid1_0_seed123` (grid 1.0°, seed 123)

| Method | Observations | Accuracy (95% CI) | Macro-F1 (95% CI) |
| --- | --- | --- | --- |
| S1-only | 949 | 89.88% (87.99%–91.78%) | 79.73% (75.81%–83.49%) |
| Geo-only | 935 | 89.41% (87.38%–91.34%) | 84.62% (80.76%–87.98%) |
| Fixed fusion | 949 | **95.79%** (94.52%–96.94%) | **93.45%** (90.60%–95.93%) |

Geo-only excluded 14 of 949. Per-genus F1 (fusion): Anastrepha 87.10% (support 28), Bactrocera 97.03% (291), Ceratitis 92.38% (197), Rhagoletis 97.27% (433).

### `reference` (M2-C, frozen — reproduced here for comparison only, not rerun)

| Method | Observations | Accuracy (95% CI) | Macro-F1 (95% CI) |
| --- | --- | --- | --- |
| S1-only | 942 | 89.92% (87.90%–91.93%) | 79.27% (74.90%–83.55%) |
| Geo-only | 927 | 89.97% (88.03%–91.80%) | 87.82% (84.64%–90.59%) |
| Fixed fusion | 942 | **95.01%** (93.63%–96.39%) | **92.52%** (89.74%–95.03%) |

## Cross-partition robustness conclusions

Across all five runs (reference + 4 new partitions):

| Method | Accuracy range | Accuracy mean | Macro-F1 range | Macro-F1 mean |
| --- | --- | --- | --- | --- |
| S1-only | 89.82%–91.75% | 90.34% | 79.73%–85.46% | 81.61% |
| Geo-only | 81.86%–91.50% | 88.37% | 77.72%–88.68% | 84.16% |
| Fixed fusion | 95.01%–96.41% | 95.63% | 92.03%–94.82% | 93.37% |

**Stable conclusion:** Fixed fusion outperformed both S1-only and Geo-only on every one of the five partitions (accuracy margin over S1-only: +3.7 to +5.6 points; over Geo-only: +4.9 to +13.7 points), and fusion's accuracy/macro-F1 are noticeably tighter across partitions (about 1.4/2.8 points of range) than either single-source method. M2-C's qualitative conclusion — that fixed fusion of the visual baseline and the geographic prior improves over either alone — held on every pre-declared spatial partition tested, not only on the single locked partition M2-C reported.

**Not stable / partition-sensitive finding:** Geo-only's own performance varied considerably more than S1-only's or fusion's across partitions — accuracy from 81.86% (`grid0_5_seed42`) to 91.50% (`grid2_0_seed42`), macro-F1 from 77.72% to 88.68%. The finer 0.5° grid (`grid0_5_seed42`) produced the weakest Geo-only result of all five partitions, on both accuracy and macro-F1, while the coarser 2.0° grid (`grid2_0_seed42`) produced the strongest. This is consistent with a finer spatial partition producing geographically smaller, more numerous test blocks whose spatial generalisation is harder for a location-only/date-aware prior, and a coarser partition producing a comparatively easier one — but this audit's design (one partition per grid scale, no repeated seeds per scale) cannot separate a genuine grid-scale effect from partition-specific sampling noise. No conclusion is drawn beyond: **Geo-only's standalone performance is not uniformly stable across the tested spatial partitions, while the fusion result is comparatively robust to that variation** (because S1-only compensates on the partitions where Geo-only is weaker).

## Ablation: location-only vs. date-aware geographic prior (reference partition only, no retrain)

M2-C's own already-trained `filts256_dateFalse` (location-only, `use_date_feats=false`) candidate from its original 4-config grid search was extracted read-only (`scripts/extract_geo_prior_candidate.py`, checkpoint SHA-256 re-verified against the recorded value) and evaluated against the **same** reference spatial-split manifest and **same** reference S1 bundle M2-C already validated — no new training, no new S1 bundle.

| Config | Geo-only observations | Geo-only accuracy | Geo-only macro-F1 | Fusion accuracy | Fusion macro-F1 |
| --- | --- | --- | --- | --- | --- |
| `filts256_dateTrue` (frozen, date-aware) | 927 (15 excluded, missing date) | 89.97% | 87.82% | 95.01% | 92.52% |
| `filts256_dateFalse` (location-only ablation) | 942 (0 excluded — no date required) | 87.05% | 85.10% | 95.54% | 93.97% |

The location-only configuration covers all 942 test observations (no date-missing exclusions), at a somewhat lower Geo-only accuracy/macro-F1 than the date-aware configuration on its own 927-observation subset. The two Geo-only figures are not on an identical observation set (927 vs. 942), so this is a directional comparison, not a controlled one. Fusion accuracy and macro-F1 are close between the two configurations (95.01%/92.52% date-aware vs. 95.54%/93.97% location-only) — within the range of variation already seen across the four new spatial partitions above, so this ablation does not show a clear, decisive advantage for either date feature choice; it is reported as a single pre-registered comparison, not as grounds to select a new preferred configuration.

## Fusion fallback behaviour (all partitions)

In every partition, `fusion` and `s1_only` observation counts are identical, and `geo_only`'s observation count is always lower by exactly the reported "excluded, missing date" figure. This confirms the same fallback mechanism M2-C documented held on every new partition: fusion never drops an observation because of a missing date — it falls back to a visual-only prediction for those cases (the `geo_support` term is simply omitted from `soft_fusion.fuse`, never fabricated).

| partition_id | Test observations | Geo-only excluded (missing date) | Fusion coverage |
| --- | --- | --- | --- |
| `reference` | 942 | 15 (1.6%) | 942/942 |
| `grid0_5_seed42` | 1,006 | 25 (2.5%) | 1,006/1,006 |
| `grid2_0_seed42` | 1,002 | 14 (1.4%) | 1,002/1,002 |
| `grid1_0_seed7` | 1,005 | 23 (2.3%) | 1,005/1,005 |
| `grid1_0_seed123` | 949 | 14 (1.5%) | 949/949 |

## Conclusions this audit cannot draw

- **No open-set, OOD, calibration, potential-incursion, false-alert, or biosecurity-efficacy conclusion.** These pre-declared spatial partitions are new random blockings of the same occurrence pool under the same `latitude_longitude_grid_v0.1` strategy — **not** temporal holdouts, not a local/non-local out-of-distribution split, and not a calibration study. No such data or pre-registered protocol exists for this milestone.
- **No new "best" model, fusion weight, or risk threshold.** Every partition trained only the one frozen recipe; the fusion formula and Prototype Implementation Profile v0.1 constants were never touched. This report's numbers are diagnostic, not a selection criterion for anything downstream.
- **No production-readiness or regulatory-decision claim.** All limitations already documented for M2-C apply unchanged (see below) and are, if anything, reinforced by the Geo-only partition-sensitivity finding above.
- **No claim distinguishing genuine grid-scale effects from single-partition sampling noise**, since each grid scale in this matrix was tested at only one seed (except 1.0°, tested at three seeds: 7, 42, 123 including the reference). A scale-vs-seed 3x3 full cross-product was explicitly out of scope for this audit (cost control).

## Limitations (carried from M2-C, plus this audit's own)

- **Small Anastrepha support** in every partition (18–31 test observations per partition): its per-genus metrics remain high-variance; treat every partition's Anastrepha row with caution.
- **iNaturalist research-grade ground truth**, not expert-verified biosecurity identification, in every partition.
- **Closed four-genus classifier** in every partition: neither S1 nor the geographic prior has an unknown-taxon class.
- **Global, label-only geographic scope**; the geographic prior uses only location (and, for the date-aware configs, date) — no environmental or seasonal-range covariates.
- **Equal-angle, not equal-area, grid cells** (`latitude_longitude_grid_v0.1`): grid cell area varies with latitude; this is not a production ecological-region definition, and different grid scales are not directly comparable in physical area across latitudes.
- **Single data source**: all partitions are re-blockings of the same underlying occurrence snapshot used by M2-C; no new external data was collected for this audit.
- **One seed per new (grid scale, non-reference) partition**: this audit cannot separate grid-scale effects from split-specific sampling noise (see "Conclusions this audit cannot draw").

## Reproduction

See `config/m2d_robustness_matrix.json` for the exact command template (`per_partition_pipeline_commands_template`, `reference_ablation_commands_template`) used to produce every result in this report, and `WorkLog.md` for the dated session log of every command actually run.
