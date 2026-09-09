# TF4 visual baseline v0.1 — temporary M2 S1 input

## Purpose and status

`flytech-reproduced-tf4-efficientnet-b2-v0.1` is an **isolated research baseline**, used only to provide a schema-compatible temporary S1 evaluation input for FlyTech S3 Milestone 2. It is not part of the S3 runtime, is not a replacement for the project's intended S1 system, and is not the original model checkpoint reported by Shen et al.

The project owner authorised this non-commercial use under `owner-approval-m2-2026-09-08`, for geographic-prior reproduction, training, and spatial-holdout evaluation. That project approval does not modify any third-party licence or permit redistribution of source images, archive, or weights.

## Provenance

- Public TF4 archive: Google Drive file `129XoNQFvoBGZ3Oor07dedT_MZnNuAdgf`.
- Archive SHA-256: `52d0705e07298c2df25739f60483a43032a3891de9042c1703daa7d610563cdf`.
- Archive size: 310,009,167 bytes (295.6 MiB); 3,409 training images: Anastrepha 671, Bactrocera 1,043, Ceratitis 747, Rhagoletis 948.
- Reference implementation: `Dukeshen1/Tephritid-Recognition` at commit `99b0198e711d68fbc64214865183b23ea374c042`.
- The public materials contain no usable TF4 test images and no original trained checkpoint. This model was therefore independently reproduced; it must never be described as the paper's released model.

## Method

EfficientNet-B2 was initialised with torchvision `IMAGENET1K_V1` weights and fine-tuned on a deterministic 10-fold TF4 manifest (fold 0 held out). Images were resized to 260×260 and ImageNet-normalised; training additionally used horizontal flip (p=0.5) and mild colour jitter. Optimisation used AdamW (learning rate 1e-4, weight decay 1e-4), class-weighted cross entropy, batch size 16, seed 42, up to 20 epochs, and patience 5.

The selected checkpoint is from epoch 14. Its SHA-256 is `b1c3c04f3748e2ab18a9966019f928e02c10b8865698215bcfad943dd4681e89`. Internal TF4 fold-0 validation was 93.00% accuracy and 93.01% macro-F1. This internal validation is not the M2 result.

## Spatial S1 evaluation bundle

The model was evaluated on 942 one-image-per-observation iNaturalist research-grade images from the M2 spatial **test** split: Anastrepha 31, Bactrocera 165, Ceratitis 371, Rhagoletis 375. Its S1-only diagnostic was 89.92% accuracy and 79.27% macro-F1 (Anastrepha F1 46.15%; Bactrocera 84.53%; Ceratitis 93.70%; Rhagoletis 92.71%). These figures are diagnostic only, not a final M2 biological-performance claim.

The bundle emits raw, closed-set softmax probabilities for exactly the four TF4 genera, mapped to stable IDs from the authorised M2 taxonomy snapshot. It has no unknown class and is complete only within that four-genus label space. Date-only observations omit `observed_at`; no midnight timestamp is invented.

Before evaluation, the preparation script excluded 234 iNaturalist test observations that matched a TF4 training observation id, 7 `no_derivatives` media records, and 19 dHash near-duplicates (64-bit difference-hash Hamming distance <=5). The resulting bundle declares zero TF4 training-observation overlap and zero SHA-256 overlap. `s1_bundle.py` verifies those declarations, artifact hashes, taxonomy crosswalk, split identity, raw-softmax semantics, and the separate labels/predictions before readiness accepts the input.

## Reproduction

From `S3-Ecological-Agent`, with the authorised local resources present:

```powershell
python scripts/prepare_tf4_s1_baseline.py
data/local/m2/s1/venv/Scripts/python.exe scripts/train_tf4_visual_baseline.py --require-cuda
data/local/m2/s1/venv/Scripts/python.exe scripts/generate_tf4_s1_outputs.py
python -m s3_ecological.cli prepare-geo-experiment --config config/geo_experiment.m2.toml --output-dir data/local/m2/readiness --overwrite
```

All images, downloaded archive, checkpoint, predictions, labels, and readiness artifacts remain under gitignored `data/local/`. The committed scripts and this card provide provenance and reproducibility without redistributing them.

## Limitations and next use

The spatial test has a small, imbalanced Anastrepha subset; ground truth is iNaturalist research-grade rather than expert re-identification; and the closed-set classifier cannot identify taxa outside TF4. It is suitable only as a clearly labelled temporary external S1 input. The next M2 increment is to reproduce/train the geographic prior on the spatial training split, select settings on validation, and run the locked spatial test once—without using the test labels for model selection or altering fusion/risk thresholds.

**Next use, done (M2-C):** this S1 bundle was re-validated against the spatial test split identity and consumed unmodified by the M2-C locked evaluation. Fixed fusion with the reproduced geographic prior raised this same S1-only diagnostic (89.92% accuracy / 79.27% macro-F1) to 95.01% accuracy / 92.52% macro-F1 on the 942-observation locked test, with the largest gain on the small Anastrepha class (F1 46.15% -> 84.85%). Full method, frozen configuration, and per-genus metrics are in `docs/model_cards/geo_prior_baseline_v0.1.md` and `docs/m2c_evaluation_report.md`. This S1 bundle itself, its limitations, and its provenance are unchanged.
