# crmms_forecasts/

Colorado River basin streamflow forecast products used as inputs to CRMMS
(the Bureau of Reclamation's Colorado River Mid-term Modeling System).
Each forecast product gets its own subfolder here, following the same
"one folder per external model" pattern as `../riverware/` elsewhere in
this repo.

Currently:
- `randomwoods/` — the RandomWoods Random Forest naturalized flow forecast
  (see its own README for details).

## randomwoods/

```
randomwoods/
├── download_inputs.py      # one script: downloads all 3 annual inputs
├── run_forecast.py         # Python wrapper that invokes the R script
├── static_data/             # CESM-LE quantile files -- static until WY2080,
│   ├── TREFHTMX_quantile_UCO_1920-2080.txt   #   committed + baked into the image
│   ├── TREFHTMN_quantile_UCO_1920-2080.txt
│   └── PRECT_quantile_UCO_1920-2080.txt
└── r/
    ├── RandomWoods_Forecast.R                # the model itself
    └── year2_randomForest_library_v1.2.1.R   # supporting R functions
```

(`static_data/` is named to avoid the repo's root `.gitignore` blanket
`data/` rule -- these files must be committed, unlike a typical scratch
`data/` folder.)

### Why one folder, self-contained

Unlike `workflows/ingests/` (which pulls data destined for the TEEHR data
warehouse), everything RandomWoods needs is scoped to this single folder:

- **`download_inputs.py`** downloads all three annually-refreshed inputs in
  one call: the USBR Lees Ferry naturalized flow workbook, and the NOAA
  AMO/PDO ocean index files. This data is used only for a single
  RandomWoods run and is never persisted to the warehouse, so it doesn't
  belong in `ingests/` alongside the warehouse-bound pulls.
- **`run_forecast.py`** invokes `r/RandomWoods_Forecast.R` via subprocess,
  passing it the directory `download_inputs.py` just populated.
- **`static_data/`** holds the CESM-LE quantile files, which don't change
  until after WY2080 -- committed here and baked into the image, no
  download needed.

### Usage

```bash
cd prefect-workflows

# 1. Download this year's inputs (once, ~Sept 25 - Oct 1, before the run)
python -m workflows.crmms_forecasts.randomwoods.download_inputs \
  --output-dir /path/to/annual_inputs

# 2. Run the forecast against them
WORK_DIR=/path/to/annual_inputs \
  LF_NATFLOW_FILE=LFnatFlow_latest.xlsx \
  FORECAST_YEAR=2027 \
  Rscript workflows/crmms_forecasts/randomwoods/r/RandomWoods_Forecast.R
```

Or via the Python wrapper:

```python
from workflows.crmms_forecasts.randomwoods.download_inputs import download_annual_inputs
from workflows.crmms_forecasts.randomwoods.run_forecast import run_r_forecast

download_annual_inputs("/path/to/annual_inputs")
run_r_forecast("/path/to/annual_inputs", end_year=2027, lf_natflow_file="LFnatFlow_latest.xlsx")
```

### Not yet wired as Prefect `@task`/`@flow`

Both `download_inputs.py` and `run_forecast.py` are plain, framework-agnostic
Python today -- no S3, no Kubernetes work-pool config, no `garden.yaml`
build/deploy entries. Wiring these up (likely a `@flow` in this folder that
chains a `@task`-wrapped `download_annual_inputs` into a `@task`-wrapped
`run_r_forecast`, following the pattern in `../../riverware/riverware_s3_workflow.py`)
is the natural next step, along with a dedicated `Dockerfile.prefect-randomwoods`
(the main `Dockerfile.prefect-teehr` image has no R) and corresponding
`garden.yaml` build block / deployment entries.
