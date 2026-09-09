# Milestone 2 Local Resource Inventory

Downloaded on 7 September 2026 for bounded, offline M2 preparation. The
project owner subsequently authorised committing this bounded resource
snapshot and the vendored third-party source to the repository. The manifest,
licence index, and reproducible downloader remain the reviewable provenance
records.

## Locations

- Public occurrence and image data: `data/external/m2/`
- Download manifest and metadata checksums:
  `data/external/m2/download-manifest.json`
- iNaturalist image provenance/licence index:
  `data/external/m2/inaturalist/image_index.csv`
- Permanent image failures:
  `data/external/m2/inaturalist/image_failures.json`
- Official `geo_prior` source: `research/third_party/geo_prior/`
- Reproducible downloader: `scripts/download_m2_resources.py`
- Offline conversion of these GBIF/ALA files into a Milestone 1.5 occurrence
  bundle and readiness run: `scripts/prepare_m2_occurrence_table.py` and
  `config/geo_experiment.m2.toml` - see
  `docs/data_cards/m2_occurrence_table_v1.md` for methodology, actual
  counts, and the readiness result obtained (M2-A,
  DesignSuggestionLog.md "2026-09-08 Australia/Sydney - M2-A")

## Downloaded resources

| Source | Local records/files | Upstream total at download time | Notes |
|---|---:|---:|---|
| GBIF Anastrepha | 9,689 | 9,689 | All coordinate-bearing results |
| GBIF Bactrocera | 10,000 | 86,669 | Bounded M2 subset |
| GBIF Ceratitis | 10,000 | 18,430 | Bounded M2 subset |
| GBIF Rhagoletis | 10,000 | 11,842 | Bounded M2 subset |
| ALA Anastrepha | 51 | 51 | Spatially valid records |
| ALA Bactrocera | 5,000 | 39,767 | ALA deep pagination stopped returning records after 5,000 |
| ALA Ceratitis | 952 | 952 | Spatially valid records |
| ALA Rhagoletis | 15 | 15 | Spatially valid records |
| iNaturalist candidate observations | 7,128 | 7,128 | Coordinate + StillImage via GBIF |
| iNaturalist medium images | 7,118 | 7,128 | One image per observation; 10 upstream 404s |

The complete local M2 data directory contains 7,133 files and 1,050,337,572
bytes. Images account for 737,676,345 bytes. There are no leaked `.partial`
files.

## `geo_prior`

The official repository is checked out at the paper-code commit:

```text
257dc7e30f3cc6bf02fbec55ee878724d077fe61
```

The local checkout is 5,525,306 bytes and includes the ocean mask, category
metadata, demo assets, training code, and evaluation code. The pretrained
`model_inat_2018_full_final.pth.tar` URL embedded in the historical demo
returned HTTP 404 on both HTTP and HTTPS on 7 September 2026, so no weight file
was substituted from an unauthenticated third party.

That upstream commit does not contain an explicit LICENSE file. See
`research/third_party/geo_prior/FlyTech_VENDORING.md`; repository inclusion
must not be interpreted as granting downstream reuse rights.

## Licence boundary

The image index preserves record and media licences separately. The successful
media licence counts are:

| Media licence | Count |
|---|---:|
| CC BY-NC 4.0 | 6,041 |
| CC BY 4.0 | 736 |
| CC0 1.0 | 189 |
| CC BY-NC-ND 4.0 | 68 |
| CC BY-NC-SA 4.0 | 51 |
| CC BY-SA 4.0 | 32 |
| CC BY-ND 4.0 | 1 |

Do not use the 69 `ND` images for transformed training data unless separately
reviewed and authorised. `NC` images also require the experiment to remain
within permitted non-commercial use. Download availability and a public
licence do not by themselves establish project-owner or supervisor approval
for an M2 experiment; the existing readiness authorisation declaration remains
authoritative.

## Reproduce or resume

```powershell
python scripts/download_m2_resources.py `
  --output-dir data/external/m2 `
  --image-workers 32
```

Existing complete files are reused. The command refreshes upstream totals,
retries missing image objects, rebuilds the image index and failure report, and
rewrites the checksum manifest.
