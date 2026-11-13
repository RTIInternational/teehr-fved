# oshbocker_1st — 1st place (oshbocker CatBoost), real-time inference

Standalone forecast package for the Water Supply Forecast Rodeo 1st-place solution using the **live-stage
(`forecast_stage_inference_live`) models**: 6 CatBoost models (yearly + monthly × q10/50/90) over SNOTEL, CDEC snow,
USGS streamflow, ACIS precipitation/temperature, UA SWANN gridded snow and monthly naturalized flow ("variant A"). No retraining.

```
core/        byte-identical live-stage solution.py, generate_predictions.py, features/, wsfr_download/   (core.sha256, SOURCE.md)
patches/     the only changes to core, applied at build (CHANGES.md): UA SWANN endpoint/format, ACIS https, package precedence, pandas-3/numpy-2 compatibility, chronological streamflow window
static/      metadata.csv, geospatial.gpkg, CDEC station list, training SNOTEL/CDEC station mappings (public competition files)
oshbocker_infer/  our code: paths, assets, build, download, monthly_flow, solution (adapter), cli
tests/       offline tests + opt-in end-to-end regression
assets.sha256  checksums of models/*.txt and feature_parameters/*.csv (552 MB; NOT in git)
```

## Runtime layout
`$WSF_ROOT` (or `--root`, default `~/wsf`) → `oshbocker_1st/`

| folder | content |
|---|---|
| `assets/models`, `assets/feature_parameters` | 6 CatBoost model files; training-derived climatologies/params (fetched, verified) |
| `build/src/` | core + patches + links to the assets (rebuilt by `build`) |
| `data/` | `metadata.csv`, `snotel/FY<y>`, `cdec/FY<y>`, `usgs_streamflow/FY<y>`, `test_monthly_naturalized_flow.csv`, `submission_format.csv` |
| `downloads/wsfr/` | raw `wsfr_download` output |
| `preprocessed/` | the core's intermediate files (`test_features.csv`, `submission_final.csv`, alternative USGS) |
| `output/<issue_date>/forecast.csv` | `site_id, issue_date, volume_10, volume_50, volume_90, model_version` (KAF) |
| `logs/predict_<issue_date>.log` | the core's log |

## Use
```bash
cd prefect-workflows/wsfr_inference
uv sync --locked --python 3.12
cd oshbocker_1st
export WSF_ROOT=/data/wsf PYTHONPATH=$PWD

uv run --project .. python -m oshbocker_infer fetch-assets --from /shared/oshbocker_1st_assets   # or s3://bucket/prefix ; verifies checksums
uv run --project .. python -m oshbocker_infer check-sources
uv run --project .. python -m oshbocker_infer run --issue-date 2026-03-01
# or:  download | build | predict   (all take --issue-date, --root)
```
Issue dates must be in January–July. `predict` exits non-zero on failed sites / invalid output (`--allow-partial` to override).
Python API: `oshbocker_infer.solution.{preprocess, predict, run_forecast}` (competition signature).

## Data sources
* **Downloaded by this package** (`wsfr_download bulk`, pinned): USGS streamflow, SNOTEL, CDEC; end = issue date (exclusive), current year always refreshed.
* **Monthly naturalized flow**: NRCS AWDB `SRVO` + NWRFC `RODW1` (Skagit); only months ended before the issue date.
* **Fetched by the core during `predict`** (patched): UA SWANN from `snowview.arizona.edu` (the old `climate.arizona.edu` service changed format and redirects), ACIS (https), alternative USGS NWIS gauges.
* Leakage check on every downloaded file; coverage and empty-feature warnings are printed (and recorded in the log).

## Known data caveats
* CDEC: ~100 of 373 mapped stations have SWE data (the rest have no sensor 82 data), as in the competition.
* American River has no usable UA SWANN SWE signal (NaN feature, same as the competition).
* SRVO real-time gaps (Ruedi, Pueblo) are warned; the models tolerate missing months.

## Validation
`tests/test_offline.py` (checksums, patches incl. SWANN parsing with the current format, leakage, schema, month logic).
`WSF_RUN_REGRESSION=1 pytest tests/test_regression.py` compares with the QC live-weights 2026 run. Results: `qc/FINDINGS.md` (Phase 3).
