# Changes relative to the original live-stage code

`core/` is byte-identical to the upstream live-stage folder (`core.sha256`). Everything below is outside `core/`.

## Patches (applied by `build`, `patches/`)
| patch | why |
|---|---|
| `001-dataloader-workers-0.patch` | `forecast_test_data.workers: 10` → `0`. Spawning 10 DataLoader workers per site/date call is slow and fails in constrained containers; results are identical (same order, no shuffling). |
| `002-multiscaler-clip-default.patch` | `libs/multiscaler.py`: after unpickling `multiscaler.pkl`, set `clip = False` on scalers that lack it. The `MaxAbsScaler` objects were pickled with sklearn 1.3.2; current scikit-learn (1.9) reads `self.clip` in `transform()` and raised `AttributeError` for every site. `False` is the parameter's default, so nothing changes on sklearn 1.3.2 or in results (py3.13 vs the pinned env: max 0.00003 % difference). |

## Behaviour added around the core (not patches)
* **sklearn pickle warning** (`solution.py`): `multiscaler.pkl` and `snotel_lrs.pkl` were pickled with sklearn 1.3.2, so newer sklearn (`environment-py313.yml`) emits `InconsistentVersionWarning` on every load. Only that warning category is silenced; on the validated 3.13 trial the forecasts matched the pinned environment to within 0.00003 %.
* **Downloads** (`download.py`): the live stage received data from the competition runtime; here SNOTEL + USGS come from the same `wsfr_download bulk` (pinned commit), end date = issue date. The downloader's regenerated `sites_to_snotel_stations.csv` is ignored; the training mapping in `static/` is used (the weights' station sets were built with it).
* **Monthly flow** (`monthly_flow.py`): NRCS AWDB SRVO + NWRFC RODW1 (Skagit), restricted to complete months before the issue date. Not part of the original runtime downloads.
* **Adapter** (`solution.py`): runs the live `solution.py` from `build/src` (chdir + sys.path, stdout suppressed), catches the core's assertions per site and records them as errors instead of writing invalid forecasts, skips sites past their season.
* **Guards**: input leakage check, checksum verification of core and weights, coverage warnings.

## Known core issues deliberately left untouched
* An empty monthly-flow file crashes the live `DataHandler`; the package never writes an empty file (it fails the download instead).
