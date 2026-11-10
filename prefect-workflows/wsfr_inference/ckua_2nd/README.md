# ckua_2nd — 2nd place (ck-ua MLP), real-time inference

Standalone forecast package for the Water Supply Forecast Rodeo 2nd-place solution, using the **live-stage
(`forecast_stage_inference_live`) weights**: median of 25 MLPs (`mlp_sumres`) with SNOTEL, USGS streamflow and
monthly naturalized flow ("variant A") inputs. No retraining.

```
core/        byte-identical copy of the live-stage solution.py, libs/, configs/   (pinned by core.sha256, see SOURCE.md)
patches/     the only changes to core, applied at build (see CHANGES.md): DataLoader workers, scaler pickle compatibility with current scikit-learn
static/      metadata.csv, geospatial.gpkg, training SNOTEL station mapping (public competition files)
ckua_infer/  our code: paths, assets, build, download, monthly_flow, solution (adapter), cli
tests/       offline tests + opt-in end-to-end regression
assets.sha256  checksums of the trained weights (the weights themselves are NOT in git, ~5 MB)
```

## Runtime layout
`$WSF_ROOT` (or `--root`, default `~/wsf`) → `ckua_2nd/`

| folder | content |
|---|---|
| `assets/results/forecast/` | `mlp_sumres-{0..24}.pth`, `multiscaler.pkl`, `snotel_lrs.pkl` (fetched, verified) |
| `build/src/` | core + patches + `results` → assets link (rebuilt by `build`) |
| `data/` | competition-runtime inputs: `metadata.csv`, `snotel/FY*`, `usgs_streamflow/FY*`, `test_monthly_naturalized_flow.csv` |
| `downloads/wsfr/` | raw `wsfr_download` output (kept separate so its regenerated SNOTEL station mapping never replaces the training mapping) |
| `output/<issue_date>/forecast.csv` | `site_id, issue_date, volume_10, volume_50, volume_90, model_version` (KAF) |

## Use
```bash
micromamba create -f environment.yml && micromamba activate ckua_infer
export WSF_ROOT=/data/wsf PYTHONPATH=$PWD          # run from inference/ckua_2nd

python -m ckua_infer fetch-assets --from /shared/ckua_2nd_assets      # or s3://bucket/prefix ; verifies checksums
python -m ckua_infer check-sources                                          # ping every data endpoint, verify response shapes (exit 1 on drift)
python -m ckua_infer run --issue-date 2026-03-01                      # download + build + predict
# or step by step:  download | build | predict   (all take --issue-date, --root)
```
`predict` exits non-zero if any site fails or the output is invalid (`--allow-partial` to override). Sites whose issue month is after
the forecast season are skipped and reported. Python API: `ckua_infer.solution.{preprocess, predict, run_forecast}`
(competition signature `predict(site_id, issue_date, assets, src_dir, data_dir, preprocessed_dir)`).

## Data sources (all downloaded by this package)
* SNOTEL, USGS daily streamflow: competition `wsfr_download bulk` (pinned commit), end date = issue date (exclusive); the current forecast year is always re-downloaded.
* Monthly naturalized flow: NRCS AWDB `SRVO` (22 sites) + NWRFC `RODW1` for Skagit. Only months that ended before the issue date are written.
  Skagit monthly flow is **required** — without it Skagit's forecast is badly off (the cause of an 11-point score gap during QC).
  San Joaquin, Merced and American have no monthly flow (as in the competition).
* A leakage check fails the download if any input row is dated on/after the issue date; coverage warnings list stations/sites/months with no data.

## Known data caveats
* SRVO has gaps for some sites in real time (e.g. Ruedi, Pueblo: missing months are printed as `WARNING monthly flow`); the model tolerates missing months.
* ~8 of 507 mapped SNOTEL stations return no data; a site whose best station set includes one loses its SNOTEL features (as in the live code).
* USGS data exists for 18 of 26 sites (same as the competition).

## Validation
`tests/test_offline.py` (checksums, patches, leakage, schema, month logic). `WSF_RUN_REGRESSION=1 pytest tests/test_regression.py`
reproduces the QC live-weights 2026 predictions exactly (diff 0.0). 2024 backtest result: see `qc/FINDINGS.md` (Phase 3 section).
