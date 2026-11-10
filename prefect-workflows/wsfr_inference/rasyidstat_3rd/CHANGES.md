# Changes relative to the original competition code

`core/` is byte-identical to the vendored 3rd place final-stage ("overall") `src/` and `configs/` (`core.sha256`, `SOURCE.md`).
The patches are listed below; none of the core's own download code is used at inference, so nothing else needed fixing in place.
Everything after the table is outside `core/`.

| patch | why |
|---|---|
| `001-no-ipython-import.patch` | `src/utils.py` imports `IPython.display.display` at module level, but it is only used by `eval_all` (notebook rendering of evaluation tables, never called at inference). Replaced by `display = print` so IPython is not a dependency. |
| `002-numpy2-nan.patch` | `np.NaN` → `np.nan` (5 places in `data/base.py`, `features/volume_obs.py`, `forecast.py`, `models/postprocess.py`). `np.NaN` was removed in numpy 2.0; `np.nan` is the same value on every numpy version. Needed for the Python 3.13 environment (`environment-py313.yml`); results there differ from the pinned environment by ≤ 0.013 % on `volume_50`. |

## Data-source fixes (in `download.py`, replacing the core's download scripts)
| source | what changed upstream | what we do |
|---|---|---|
| UA SWANN daily NetCDF | The file suffix now depends on the age of the day: `_early` (current month), `_provisional` (1-6 months), `_stable` (older). The core's `_parse_uaswann_daily_url` hard-codes `_stable`, which 404s for recent days; it also disables TLS verification. | Try `_stable`, `_provisional`, `_early` in that order, keep the tier per day, upgrade files when a better tier appears; TLS verification on. Same 4 km grid / variables, so the core's basin reduction is unchanged. |
| UA SWANN HUC6/HUC8 | `climate.arizona.edu/snowview/csv/...` redirects to `snowview.arizona.edu`, with `#` comment header and renamed columns (`overall_mean_swe_in`, `overall_cumulative_precip_in`, ...). Values identical to the old files (max abs diff 0.0 over 1981-2026). | Download from the new host and write the legacy file layout (`Date`, `Average SWE (in)`, `Average Accumulated Water Year PPT (in)`), so the core's `preprocess_uaswe_huc` runs untouched. |
| ERA5-Land | Core downloads whole months of issue-date-minus-one days. | Only the day before the issue date is requested (the only day the features read), same request as `src.data.cds.download_era5` (`netcdf_legacy` zip, 00:00/23:00, CONUS box); one file per day. |
| SEAS5.1 | none | Same request as `src.data.cds.download_seas51_monthly`, for the initialisations Dec(y-1) .. issue month only. |
| USBR RISE | none | Core `download_usbr`, always re-fetched, exactly one file per site (the core's reader sums duplicate dates). |
| SNOTEL / CDEC / USGS / PDSI | none | The competition's `wsfr_download` functions with the 3rd place call parameters (own SNOTEL station list, PDSI from Dec 1); SNOTEL/CDEC/USGS are fetched through the issue day itself (its row must exist; every feature reads values lagged by >= 1 day), PDSI up to the day before; always re-fetched. `wsfr_download.config` does `logger.remove(0)` at import, which raises once the core has touched loguru, so it is imported through a tolerant guard. |
| Monthly flow (variant A) | n/a | `monthly_flow.py`: NRCS AWDB `SRVO` + NWRFC `RODW1` (Skagit), months ended before the issue date. Requests are retried (4 attempts, backoff) on 403/429/5xx/timeouts: the NRCS server intermittently rejects one of the ~22 sequential requests, which otherwise discarded the whole file. |

## Inference path (`engine.py`, promoted from the QC wrapper)
The core's `train_cv.py` is a module-level training script, so the feature path it applies at prediction time is transcribed
step by step (same configs, `exclude_years` 2011/2015, scaling/diff, per-basin site ranking from the saved artifacts, Tweedie "reg" model as p50, `ens_all`).
Differences from the QC wrapper (`models/rasyidstat_lgbm/forecast`), none of which change the numbers (2026 outputs identical, diff 0.0; `tests/reference/`):
* No historical 1981-2023 data. Every feature is a per (site, water year) quantity, and training statistics come from the saved model artifacts, so only the forecast water year is read (16 GB of history and 683 MB of caches dropped).
* Rows are restricted to the issue date before the SWE features are built (the model is row-wise).
* PDSI: for a January issue the newest PDSI row can still be dated in the previous calendar year, which makes the core's `expand_date` produce an empty range and crash. A NaN row on Jan 1 of the water year anchors the range (the following `ffill` makes it a no-op).
* A variant whose inputs do not cover the issue date is left out of the ensemble and reported (the wrapper silently produced no rows).

## Real-time behaviour (not in the competition)
* Sources have different latencies (ERA5-Land ~5 days, UA SWANN ~2 days, SEAS5.1 published ~5th of the month). On the issue date itself only some of the 9 variants can run; the others are dropped with a warning and `model_version` becomes `..._partial<N>of9`. `--strict` fails instead. A full 9-variant ensemble needs a run about 6+ days after the issue date.
* Guards: January-July issue dates only, input leakage check, core/asset checksum verification, per-source freshness report.
