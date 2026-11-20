Upstream: 2nd place (ck-ua) Water Supply Forecast Rodeo, Final Prize Stage forecast-stage submission
("forecast_stage_inference_live", the weights/code the winner submitted for live forecasting).

Source folder: `.../Experimental_Forecasts/forecast_stage_inference_live/forecast-2nd-ck-ua/` (shared drive).
`solution.py`, `libs/`, `configs/` are copied byte-for-byte (excluding `__pycache__` and `results/`).
The weights (`results/forecast/*`) are not in git; see `../assets.sha256`.

`../core.sha256` pins every file here; `python -m ckua_infer check-assets` and the build fail if any file differs.
Deviations from upstream live ONLY in `../patches/` (see `../CHANGES.md`).
