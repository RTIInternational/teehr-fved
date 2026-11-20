# Inference models: summary

Three standalone real-time forecast packages for the top solutions of the DrivenData *Water Supply Forecast Rodeo* (Final Prize Stage).
Each downloads its own inputs, runs the trained model for an issue date (January-July) and writes `output/<issue_date>/forecast.csv`
with `site_id, issue_date, volume_10, volume_50, volume_90, model_version` (KAF, 26 sites). No retraining. Status as of 2026-11-03.

## At a glance

| | 1st place | 2nd place | 3rd place |
|---|---|---|---|
| Author | oshbocker | ck-ua | rasyidstat |
| Package | `oshbocker_1st/` (`oshbocker_infer`) | `ckua_2nd/` (`ckua_infer`) | `rasyidstat_3rd/` (`rasyidstat_infer`) |
| Model | CatBoost, 6 models (yearly + monthly x q10/50/90) | MLP (`mlp_sumres`), median of 25 networks | LightGBM, 9 variants averaged (`ens_all`) |
| Weights used | live stage (`forecast_stage_inference_live`) | live stage | overall-config run, trained 1981-2023 (the QC wrapper's weights) |
| Assets (not in git) | 552 MB (`models`, 541 MB `feature_parameters`) | ~5 MB | 172 MB (9 variant folders) |
| Core code | `solution.py`, `generate_predictions.py`, `features/`, bundled `wsfr_download/` | `solution.py`, `libs/`, `configs/` | `src/` + `configs/` of the overall solution |
| Patches to core | 3 | 1 | 0 (inference path transcribed in `engine.py`) |
| Run time (one date) | not timed here | not timed here | ~4 s predict; downloads dominate (~20 min on an empty root, mostly CDS queue time) |

## Inputs

| Source | 1st | 2nd | 3rd |
|---|---|---|---|
| SNOTEL (NRCS AWDB) | yes | yes | yes |
| CDEC snow | yes | no | yes |
| USGS streamflow (NWIS) | yes (+ alternative gauges) | yes | yes |
| Monthly naturalized flow (variant A: NRCS `SRVO`, NWRFC `RODW1` for Skagit) | yes | yes | yes |
| UA SWANN | SnowView HUC time series | none | HUC6/8 time series + gridded daily NetCDF (4 of 9 variants) |
| ACIS precipitation / temperature | yes | no | no |
| PDSI (gridMET) | no | no | yes |
| USBR RISE (4 reservoir inflows) | no | no | yes |
| ERA5-Land, SEAS5.1 (Copernicus CDS, needs `~/.cdsapirc`) | no | no | yes |

## Validation against the earlier QC runs (fresh root, own downloads)

| Package | Result |
|---|---|
| 2nd | 2024 backtest (28 dates, variant A): **57.03** all sites / **76.04** priority sites, equal to the live reference; 2026 forward run identical |
| 1st | 2024-03/04/05-01 bit-identical to the live reference (reference live score 58.57 / 67.29); 2026-03-01 within 0.1% (Detroit only, uninvestigated) |
| 3rd | 2026-03-01 end to end from an empty root: 9 variants, 26 rows, bit-identical to the QC wrapper (2024 wrapper score 60.74 / 76.59; 2026 124.08 / 149.26) |

Scores are the competition quantile loss (lower is better). 2026 reference scores of the same weights, 1st-of-month Jan-Apr, all / priority sites:
1st 100.54 / 110.37, 2nd 151.25 / 191.05, 3rd 124.08 / 149.26 (one low-snow year, four dates: not a ranking).

## Data-source fixes made (details in each `CHANGES.md`)
- **UA SWANN HUC series** (1st, 3rd): moved to `snowview.arizona.edu`, new column names; values identical to the old files.
- **UA SWANN gridded daily files** (3rd): suffix depends on file age (`_early` / `_provisional` / `_stable`); the package tries all and upgrades later.
- **ACIS** (1st): https + timeout.
- **`wsfr_download`** (3rd): tolerant import (its config crashed once loguru had been touched); SNOTEL/CDEC/USGS fetched through the issue day.
- **Monthly flow** added to all three.

## Real-time behaviour
- 1st and 2nd place need only same-day-ish data (SNOTEL, CDEC, USGS, ACIS, SnowView, monthly flow) and can run on the issue date. The monthly flow of the last complete month depends on when SRVO / NWRFC publish it (not yet confirmed).
- 3rd place needs ERA5-Land (~5 days after the issue date) and SEAS5.1 (published ~5th of the month) for 6 of its 9 variants. Without them 3 variants run (`base_swe`, `swe_ua`, `ngm_ua`) and `model_version` ends in `_partial3of9`; a full ensemble needs a run about 6+ days after the 1st. `--strict` turns a missing variant into an error. **Policy (forecast early with a partial ensemble vs wait) is still to be decided.**
- The 1st-place live models can emit unordered quantiles; the adapter sorts them and warns. American River has no UA SWE signal (NaN feature, as in the competition).

## Common commands (run from the package folder, `PYTHONPATH=$PWD`)
```
python -m <pkg>_infer fetch-assets --from <dir or s3://...>   # copy + checksum-verify weights
python -m <pkg>_infer check-sources                           # ping every data endpoint, verify response shape
python -m <pkg>_infer run --issue-date 2026-03-01 --root DIR  # build + download (+ preprocess) + predict
```
Other commands: `build`, `check-assets`, `download`, `predict` (3rd also `preprocess`), `manifest` (maintainers). Python API: `<pkg>_infer.solution`.

## Conventions shared by all packages
`core/` is byte-identical to the competitor code (`core.sha256`); every change is a numbered patch in `patches/` or code outside `core/`.
Runtime root `$WSF_ROOT/<package>/{assets,data,downloads,preprocessed,output,logs}`. Inputs are cut at the issue date (leakage check on download).
Packages are self-contained (no cross-package imports). Tests: `tests/test_offline.py` (checksums, schema, leakage, endpoint logic) and opt-in
`WSF_RUN_REGRESSION=1 tests/test_regression.py`. Full findings: `../qc/FINDINGS.md` (Phase 3).

## Not done
Prefect flows and Docker images; retraining; permanent storage for the weights (currently `~/wsf-assets/<package>/` on the dev machine).
