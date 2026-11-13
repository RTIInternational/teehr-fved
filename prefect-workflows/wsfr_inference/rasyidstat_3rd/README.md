# rasyidstat_3rd — 3rd place (rasyidstat LightGBM ensemble), real-time inference

Standalone forecast package for the Water Supply Forecast Rodeo 3rd-place Final Prize Stage solution (`overall` phase):
**9 LightGBM variants** (each: q10/q50/q90 + a Tweedie "reg" model used as the median), combined into the `ens_all`
ensemble. Inputs: SNOTEL, CDEC snow, USGS and USBR flows, PDSI, UA SWANN (HUC time series + gridded), ERA5-Land, SEAS5.1 and monthly
naturalized flow ("variant A"). The models are the QC wrapper's overall-config training run (trained through 2023). No retraining.

```
core/        byte-identical competition src/ and configs/ (core.sha256, SOURCE.md); patches in patches/ (CHANGES.md)
static/      public metadata + the solution's own site/station metadata (data/meta, data/raw of the competition folder)
rasyidstat_infer/  our code: paths, build, download, preprocess, engine (inference path), solution (adapter), monthly_flow, cli
tests/       offline tests + opt-in end-to-end regression (tests/reference = QC wrapper 2026 output)
assets.sha256  checksums of the 9 trained variants (172 MB; NOT in git)
```

## Runtime layout
`$WSF_ROOT` (or `--root`, default `~/wsf`) → `rasyidstat_3rd/`

| folder | content |
|---|---|
| `assets/models/<variant>/` | 9 variants: LightGBM boosters, feature names, scale factors, training statistics, selected SNOTEL/CDEC sites (fetched, verified) |
| `build/src/` | core + static metadata + links to `assets/models` and `downloads/` (rebuilt by `build`); the model's working directory |
| `downloads/` | forecast-water-year raw inputs: `snotel/ cdec/ usgs_streamflow/ usbr/ pdsi/ uaswann/{raw/daily,raw/huc6,raw/huc8} era5/ seas51/` |
| `preprocessed/` | feature caches reduced from `downloads/` (`pdsi.csv`, `uaswe_huc{6,8}.feather`, `uaswe_basin.csv`, `era5.feather`, `seas51.feather`) |
| `data/` | `metadata.csv`, `test_monthly_naturalized_flow.csv` (monthly flow), copies of the public files used by `wsfr_download` |
| `output/<issue_date>/forecast.csv` | `site_id, issue_date, volume_10, volume_50, volume_90, model_version` (KAF) |
| `logs/predict_<issue_date>.log` | |

Only the forecast water year is downloaded: every feature is a per-(site, water year) quantity and the training statistics come from the
saved artifacts, so the 16 GB of historical data the training run used is not needed.

## Use
```bash
cd prefect-workflows/wsfr_inference
uv sync --locked --python 3.12
cd rasyidstat_3rd
export WSF_ROOT=/data/wsf PYTHONPATH=$PWD                                         # needs ~/.cdsapirc for ERA5-Land / SEAS5.1

uv run --project .. python -m rasyidstat_infer fetch-assets --from /shared/rasyidstat_3rd_assets      # or s3://bucket/prefix ; verifies checksums
uv run --project .. python -m rasyidstat_infer check-sources
uv run --project .. python -m rasyidstat_infer run --issue-date 2026-03-01
# or step by step:  build | download [--sources ...] | preprocess [--sources ...] | predict      (all take --issue-date, --root)
```
Issue dates must be in January–July. Python API: `rasyidstat_infer.solution.{preprocess, predict}`.

## Real-time availability (read this before scheduling runs)
The inputs have different latencies, and the model must see the data lagged exactly as in training:

| input | needs | typical availability |
|---|---|---|
| SNOTEL, CDEC, USGS | a row for the issue day (its value is never a feature, features lag >= 1 day) | SNOTEL/CDEC: the morning of the issue day; USGS: provisional, partial day |
| USBR, PDSI | day before the issue date | next day |
| UA SWANN (HUC + gridded) | day before the issue date (the issue day row is generated) | ~2 days |
| ERA5-Land | 00:00 UTC of the day before the issue date | ~5 days |
| SEAS5.1 | the issue month's own initialisation | published about the 5th of the month |

A variant whose inputs do not cover the issue date is **left out of the ensemble with a warning** (never filled from stale data), and
`model_version` becomes `rasyidstat_3rd_overall_ens9_to2023_partial<N>of9`. Without ERA5-Land and SEAS5.1 only `base_swe`, `swe_ua` and
`ngm_ua` run (3 of 9; verified); a complete 9-variant ensemble needs a run about a week after the 1st. `--strict` turns any left-out
variant into an error. Whether to forecast on the issue day with fewer variants or wait for the full ensemble is an operational decision.

## Data sources
SNOTEL/CDEC/USGS/PDSI: competition `wsfr_download` (pinned). USBR RISE: core downloader. UA SWANN gridded: `climate.arizona.edu` daily NetCDF
(`_stable`/`_provisional`/`_early` tiers) and HUC series from `snowview.arizona.edu`. ERA5-Land and SEAS5.1: Copernicus CDS.
Monthly flow: NRCS AWDB `SRVO` + NWRFC `RODW1` (Skagit). Details of what differs from the competition-era downloaders: `CHANGES.md`.

## Known caveats
* Early/provisional UA SWANN values are revised later; the model was trained on stable data. Files are upgraded automatically on later runs.
* CDEC: only part of the mapped stations carry SWE data, as in the competition.
* ERA5-Land and SEAS5.1 requests go through the CDS queue (minutes to an hour for the SEAS5.1 months on a fresh root; later runs only fetch new data).

## Validation
`tests/test_offline.py`: checksums, patch list, schema, leakage, SWANN tier fallback, HUC format conversion, partial-ensemble labelling.
`WSF_RUN_REGRESSION=1 pytest tests/test_regression.py` re-runs the 2026 dates from an empty root against the QC wrapper output.
Equivalence and scores: `qc/FINDINGS.md` (Phase 3).
Verified end to end: an empty root, `run --issue-date 2026-03-01` (all inputs freshly downloaded, ~20 min mostly CDS queue time) gives 26 rows
with all 9 variants, **bit-identical** to the QC wrapper output; a root without ERA5/SEAS5.1 gives the 3-of-9 partial ensemble.
