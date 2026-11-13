# Running the inference packages

Step-by-step guide to producing a forecast with any of the three standalone packages. For what each model is, see
[`MODELS_SUMMARY.md`](MODELS_SUMMARY.md); for package internals see the `README.md` in each folder.

| Place | Folder | Python package | Env name |
|---|---|---|---|
| 1st | `oshbocker_1st/` | `oshbocker_infer` | `oshbocker_infer` |
| 2nd | `ckua_2nd/` | `ckua_infer` | `ckua_infer` |
| 3rd | `rasyidstat_3rd/` | `rasyidstat_infer` | `rasyidstat_infer` |

Every package: downloads its own inputs for an issue date, runs the trained model, and writes
`$WSF_ROOT/<folder>/output/<issue_date>/forecast.csv` (`site_id, issue_date, volume_10, volume_50, volume_90, model_version`; KAF; 26 sites).

## 1. Prerequisites

- Linux/macOS (WSL works), internet access, `micromamba` (or conda/mamba), GNU `patch` (installed by the env files).
- Disk: 1st ≈ 552 MB of weights, 2nd ≈ 5 MB, 3rd ≈ 172 MB, plus downloaded data under the root.
- **3rd place only:** a Copernicus CDS account with the ERA5-Land and SEAS5 licences accepted, and `~/.cdsapirc`
  (or `CDSAPI_URL` / `CDSAPI_KEY`). Without it only 3 of the 9 variants can run (see [Timing](#5-timing-3rd-place-needs-patience)).
- Trained weights ("assets") are **not in git**. Get the shared assets location from the maintainers (`~/wsf-assets/<folder>/` on the dev machine, or an `s3://` prefix).

## 2. One-time setup (per package)

Run everything from the package folder. Replace the three `<...>` values from the table above.

```bash
cd inference/<folder>
micromamba create -f environment.yml
eval "$(micromamba shell hook --shell bash)"
micromamba activate <env name>

export WSF_ROOT=/data/wsf          # work root; default is ~/wsf; --root overrides per command
export PYTHONPATH=$PWD             # required: lets `python -m <package>` find the code

python -m <package> fetch-assets --from ~/wsf-assets/<folder>   # or s3://bucket/prefix; copies and verifies checksums
python -m <package> check-sources                                  # optional: pings every endpoint, exit 1 on drift
```

`fetch-assets` is only needed once per root (re-run to repair; `check-assets` re-verifies without copying).

### What to pass to `fetch-assets --from`

Pass the **per-model folder** (not `~/wsf-assets` itself). Its contents are rsynced into `$WSF_ROOT/<folder>/assets/`, then checksum-verified.

| Package | `--from` | Contents expected there |
|---|---|---|
| `oshbocker_infer` | `~/wsf-assets/oshbocker_1st` | `models/`, `feature_parameters/` |
| `ckua_infer` | `~/wsf-assets/ckua_2nd` | `results/forecast/` (`mlp_sumres-{0..24}.pth`, `multiscaler.pkl`, `snotel_lrs.pkl`) |
| `rasyidstat_infer` | `~/wsf-assets/rasyidstat_3rd` | `models/<variant>/` (9 variants) |

```bash
python -m oshbocker_infer   fetch-assets --from ~/wsf-assets/oshbocker_1st
python -m ckua_infer        fetch-assets --from ~/wsf-assets/ckua_2nd
python -m rasyidstat_infer  fetch-assets --from ~/wsf-assets/rasyidstat_3rd
```

Local directories need `rsync`; `s3://` sources need the AWS CLI (`aws s3 sync`). Use an absolute path (a literal `~` is only expanded by your shell).

### Shared Python 3.12 environment with uv

[`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) provide one environment for all three packages without conda or
micromamba. The package list comes from [`environment-py313.yml`](environment-py313.yml), with its versions used as upper
bounds so uv can select Python 3.12-compatible releases (for example, rioxarray 0.24.0 requires Python 3.13). The lockfile
records exact resolved versions and CPU-only PyTorch. `wsfr-download` is pinned to commit
`9f6e29d3f3157b7be2281ce2811bfd23c2988f2b` of the
[maintained fork](https://github.com/pdmich/water-supply-forecast-rodeo-runtime), which uses the modern USGS API;
`wsfr-read` retains its original competition revision. GNU `patch` is a system prerequisite, not a Python dependency;
install it separately if needed.

```bash
cd inference
uv sync --locked --python 3.12
source .venv/bin/activate
# Then cd into a package folder, export PYTHONPATH=$PWD, and run python -m <package> as above.
```

The environment lives at `inference/.venv`; `.python-version` selects Python 3.12. To recreate it, run the same `uv sync`
command. This environment still needs manual model validation; the conda environments remain available as references.

### Optional: one shared Python 3.13 environment for all three packages

[`environment-py313.yml`](environment-py313.yml) (env `wsf_py313`) replaces the three per-package Python 3.10 environments with a single
one using current library versions (numpy 2, pandas 3, scikit-learn 1.9, torch 2.14 CPU, lightgbm 4, geopandas 1.2, ...). The models are
not retrained; the code differences are handled by the patches in each package's `patches/` (see each `CHANGES.md`).

```bash
cd inference
micromamba create -f environment-py313.yml
micromamba activate wsf_py313
# then, per package, from its folder: export PYTHONPATH=$PWD and run `python -m <package> ...` exactly as above
```

The per-package `environment.yml` files stay the reference environments. In the trial runs (issue date 2026-04-01, before the final
patch set was re-run end to end), `wsf_py313` matched them to within 0.013 % on `volume_50` for the 2nd and 3rd place. For the 1st place,
patches `004`-`006` make the features independent of the pandas version; `006` changes the 30-day streamflow feature for some sites
versus the original submission (see `oshbocker_1st/CHANGES.md`).

## 3. Produce a forecast

```bash
python -m <package> run --issue-date 2026-03-01
```

`run` = build (if needed) + download + (3rd: preprocess +) predict. Issue dates must be in **January–July**.
Output: `$WSF_ROOT/<folder>/output/2026-03-01/forecast.csv`; log: `.../logs/predict_<issue_date>.log` (1st and 3rd).

Quick start for all three, once each env/assets are set up:

```bash
for p in oshbocker_1st:oshbocker_infer ckua_2nd:ckua_infer rasyidstat_3rd:rasyidstat_infer; do
  (cd inference/${p%%:*} && PYTHONPATH=$PWD micromamba run -n ${p##*:} python -m ${p##*:} run --issue-date 2026-03-01 --root "$WSF_ROOT")
done
```

### Step by step

| Command | What it does |
|---|---|
| `fetch-assets --from SRC` | Copy weights from a directory or `s3://` URI and verify against `assets.sha256` |
| `check-assets` | Verify assets and `core/` against `assets.sha256` / `core.sha256` |
| `check-sources [--sources ...]` | Ping each data endpoint and verify response shape |
| `build` | Assemble `build/src` = `core/` + `patches/` + asset links (rebuilt on demand) |
| `download --issue-date D [--sources ...]` | Fetch inputs, cut at the issue date, leakage-checked (3rd: `--sources` selects steps) |
| `preprocess --issue-date D` | **3rd only.** Reduce downloads to feature caches |
| `predict --issue-date D` | Forecast all sites → `forecast.csv` |
| `manifest` | Maintainers only: rewrite checksum manifests |

### Options

| Flag | Applies to | Effect |
|---|---|---|
| `--root DIR` | all | Work root (default `$WSF_ROOT`, else `~/wsf`) |
| `--issue-date YYYY-MM-DD` | download / predict / run | Forecast date (Jan–Jul) |
| `--sites ID [ID ...]` | predict / run | Limit to some sites |
| `--out FILE` | predict / run | Write the CSV somewhere other than the default path |
| `--allow-partial` | predict / run | Exit 0 even if some sites failed (default: exit 2 on failed sites or invalid output) |
| `--no-refresh` | 1st, 2nd `download` | Keep existing current-year files instead of re-downloading |
| `--strict` | 3rd | Error out if any variant must be left out (default: leave out and warn) |

## 4. Check the result

```bash
python - <<'EOF'
import pandas as pd
df = pd.read_csv("/data/wsf/<folder>/output/2026-03-01/forecast.csv")
print(df.shape)                       # expect (26, 6)
print(df.model_version.unique())      # 3rd: look for "_partial<N>of9"
print(df.head())
EOF
```

Exit code `0` = success; `2` = failed sites or invalid output; any `WARNING` lines on stderr (missing monthly flow, sorted quantiles,
left-out variants) are worth reading but are not fatal.

## 5. Timing (3rd place needs patience)

| Package | Needs data from | Run when |
|---|---|---|
| 1st, 2nd | SNOTEL, CDEC (1st), USGS, ACIS/SnowView (1st), monthly flow | on the issue date |
| 3rd | + ERA5-Land (~5 days after the issue date) and SEAS5.1 (published ~5th of month) for 6 of 9 variants | **6+ days after the 1st** for the full ensemble |

Run 3rd place earlier and it silently runs the 3 variants whose inputs exist (`base_swe`, `swe_ua`, `ngm_ua`); `model_version`
then ends in `_partial3of9`. Use `--strict` to fail instead. First 3rd-place run on an empty root takes ~20 min (CDS queue);
later runs fetch only new data. 1st place `run` takes ~4 min.

## 6. Reruns, clean-up, tests

- Re-running a date is safe: current-forecast-year inputs are refreshed (unless `--no-refresh`), `build/` is regenerated, output is overwritten.
- Use a separate `--root` per experiment to avoid mixing data; deleting a root's `downloads/` and `preprocessed/` forces fresh inputs
  (weights in `assets/` are kept).
- Offline tests (no network): `pytest tests/test_offline.py`
- Source-drift tests: `pytest tests/test_check_sources.py`
- End-to-end regression against the QC reference (network, slow): `WSF_RUN_REGRESSION=1 pytest tests/test_regression.py`

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `No module named <package>` | Not in the package folder or `PYTHONPATH=$PWD` not set |
| Checksum mismatch on `fetch-assets` | Incomplete/wrong asset copy; re-fetch from the shared source |
| `check-sources` exits 1 | An upstream endpoint changed format or is down; see that package's `CHANGES.md` before running |
| "leakage" error in `download` | An input row is dated on/after the issue date; do not override — investigate the source |
| `ERROR output:` / exit 2 | Some site failed or schema invalid; read the log, rerun, or `--allow-partial` if acceptable |
| `WARNING monthly flow` for Ruedi / Pueblo | Known SRVO real-time gap; model tolerates missing months |
| Skagit forecast far off (2nd) | Skagit monthly flow (NWRFC `RODW1`) is missing — it is required |
| 3rd: `_partial3of9` | ERA5-Land / SEAS5.1 not yet published, or `~/.cdsapirc` missing / licences not accepted |
| 3rd: CDS request stuck | Normal queueing (minutes to an hour on a fresh root); wait or rerun |
| `patch: command not found` during `build` | Install GNU `patch` (`apt install patch`) |
