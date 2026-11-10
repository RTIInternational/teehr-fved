# Changes relative to the original live-stage code

`core/` is byte-identical to the upstream live-stage folder (`core.sha256`). Everything below is outside `core/`.

## Patches (applied by `build`, `patches/`)
| patch | why |
|---|---|
| `001-wsfr-download-package-precedence.patch` | Adds `wsfr_download/__init__.py` so the bundled module (which has `download_alternative_usgs_streamflow`) shadows the pip-installed `wsfr_download` (which lacks it). Needed to import the core's `streamflow_deviation.py`. |
| `002-ua-swann-new-endpoint-and-format.patch` | **UA SWANN service changed.** `climate.arizona.edu/snowview/csv/Download/Watersheds/` now redirects to `snowview.arizona.edu/...` and returns a `#` comment header plus 5 columns (`date, water_year, overall_cumulative_precip_in, overall_mean_swe_in, overall_snow_covered_area_sq_mi`) instead of 3 columns; the original `.columns = [...]` assignment fails on it. The patch targets the new host, drops `verify=False`, adds a timeout / `raise_for_status`, skips comments and selects the precipitation and SWE columns by name. Values are identical to the old service for the overlapping history (checked on Libby 1981-2026: max abs diff 0.0). |
| `003-acis-https-timeout.patch` | ACIS POST moved to https with a 120 s timeout and `raise_for_status` (an unattended real-time run must not hang or parse an HTML error page). Behaviour otherwise unchanged. |
| `004-explicit-mean-std-agg.patch` | `.agg([np.mean, np.std])` → `.agg(['mean', 'std'])` in the six deviation baselines (ACIS precip/temp, CDEC, SNOTEL, streamflow, UA SWANN). pandas 2.1 mapped `np.std` to the sample std (ddof=1); pandas ≥ 3 calls `np.std` directly (ddof=0), which silently changes every deviation feature. The string `'std'` is ddof=1 on every version, so results are unchanged on the pinned pandas 2.1. |
| `005-cdec-element-means-iloc.patch` | `element_means[idx]` → `element_means.iloc[idx]` in `cdec_deviation.py`. Integer lookup on a string-labelled Series was a positional fallback removed in pandas 3 (`KeyError: 0`). Same result on pandas 2.1. |
| `006-streamflow-window-chronological.patch` | **Fixes a train/inference mismatch in the original live-stage code.** `streamflow_deviation_30_mean` takes `sub_df[-30:]` after an inner `pd.merge`, i.e. it assumes chronological row order. Training (`vendor/oshbocker_catboost_1st/training/features/streamflow_deviation.py`) sorts by `site_id, datetime` before a rolling 30-day mean, and the training features in `cv_features.csv` match the chronological value (mean abs. difference ≈ 0.01 vs ≈ 0.6–0.7 for the merge order of pandas 2.1). pandas 2.1 returned the merge in grouped-by-`month_day` order for some sites, so the model saw a different feature than it was trained on; pandas 3 preserves the left order. The patch sorts by `datetime` first, which makes the feature identical on every pandas version and equal to the training definition. **Forecast values change versus the original submission for the affected sites** (observed for `pueblo_reservoir_inflow` and `fontenelle_reservoir_inflow` on 2026-04-01). The other `[-window:]` slices (ACIS, CDEC, SNOTEL) aggregate with `groupby(...date)` first and are already date-sorted. |

## Behaviour added around the core (not patches)
* **Downloads** (`download.py`): USGS, SNOTEL, CDEC via the competition `wsfr_download bulk` (pinned commit; the live stage received this data from the runtime), end date = issue date. The CDEC/SNOTEL mappings from training (`static/`) replace the regenerated ones. Monthly flow (variant A) from `monthly_flow.py`.
* **Adapter** (`solution.py`): builds a one-date `submission_format.csv`, runs the live `solution.preprocess` once and keeps only the issue date, drops sites past their season, sorts quantiles if the live output is mis-ordered (warns), and warns when a key feature is empty for a site.
* **Guards**: January–July issue dates only, input leakage check, core/asset checksum verification, coverage warnings.
* Official competition `metadata.csv` is used (the QC wrapper had alternate USGS ids pre-applied; the live `update_metadata` applies its own overrides anyway and the alternate gauges are downloaded by the core).

## Known behaviours of the core that are left untouched
* `american_river_folsom_lake` has essentially no UA SWE signal (SWANN SWE ≤ 0.02 in over the whole history ⇒ std 0 on most days ⇒ NaN deviation); CatBoost treats it as missing, as in the competition.
* The core re-downloads the alternative USGS (NWIS) gauges on every `preprocess` call.
