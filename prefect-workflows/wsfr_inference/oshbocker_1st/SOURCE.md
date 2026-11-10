Upstream: 1st place (oshbocker) Water Supply Forecast Rodeo, Final Prize Stage forecast-stage submission
("forecast_stage_inference_live": 6 CatBoost models, forecast-phase feature code with CDEC snow, ACIS and UA SWANN).

Source folder: `.../Experimental_Forecasts/forecast_stage_inference_live/forecast-1st-oshbocker/` (shared drive).
`solution.py`, `generate_predictions.py`, `features/` and the bundled `wsfr_download/` (alternative USGS download) are
copied byte-for-byte (excluding `__pycache__`, `models/` and `feature_parameters/`).
The model files (`models/*.txt`) and training-derived parameters (`feature_parameters/*.csv`, 541 MB) are not in git; see `assets.sha256`.

`core.sha256` pins every file under `core/`; `python -m oshbocker_infer check-assets` and the build fail if any file differs.
Deviations from upstream live ONLY in `patches/` (see `CHANGES.md`).
