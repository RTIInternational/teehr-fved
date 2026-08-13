# RiverWare / CRMMS

Python package for running the CRMMS RiverWare model and postprocessing its outputs. Scripts are deployed to the RiverWare Windows EC2 instance and invoked remotely via AWS SSM from the Prefect workflow in [`prefect-workflows/workflows/riverware/`](../prefect-workflows/workflows/riverware/).

## Folder Structure

```
riverware/
├── run_pipeline.py              # ← Prefect entrypoint: execute model + postprocess → Parquet
│
├── execution/
│   └── run_crmms.py             # Generate .rcl, launch RiverWare in batch mode, tail run.log
│
├── postprocessing/
│   ├── extract_outputs.py       # Parse all .rdf files → TEEHR-schema DataFrame
│   └── load_results.py          # run_postprocessing() entry point; optional Parquet output
│
├── utils/
│   └── riverware_utils.py       # RDF state-machine parser; reference-time extractor from run.log
│
└── tests/
    ├── conftest.py              # Shared pytest fixtures (session-scoped model_dir, rdf_dir, etc.)
    ├── test_load_results.py     # Regression tests for run_postprocessing
    └── explore_outputs.ipynb   # QA/QC notebook — schema checks, spaghetti/fan plots, exceedance curves
```

## Workflow

1. **Execution** — `run_crmms.py` writes an RCL script, launches `RiverWare.exe --batch`, and streams `run.log` to stdout, printing per-trace progress and raising on error.
2. **Postprocessing** — `run_postprocessing()` reads `rdfOutput/*.rdf` and `run.log`, returns a [TEEHR secondary timeseries](https://github.com/RTIInternational/teehr) schema DataFrame, and optionally writes a Parquet file.

`run_pipeline.py` orchestrates both steps and is the single script invoked by Prefect.

## Output Schema

`run_postprocessing()` returns a `pandas.DataFrame` with these columns:

| Column | Type | Description |
|---|---|---|
| `reference_time` | `datetime64[us, UTC]` | Model init date (from `run.log` `Begin date`) |
| `value_time` | `datetime64[us, UTC]` | Simulation timestep (RiverWare 24:00 → next-day UTC) |
| `configuration_name` | `str` | Caller-supplied label (e.g. `"crmms_esp_march2025"`) |
| `unit_name` | `str` | RiverWare slot units (e.g. `"ft"`, `"acre-ft"`) |
| `variable_name` | `str` | TEEHR variable name. Common slots are mapped via `CRMMS_VARIABLE_MAP` (e.g. `"pool_elevation_monthly_eop"`, `"inflow_monthly_total"`). Unmapped slots fall back to snake_case of the RiverWare slot name. Override with `variable_name_map=`. |
| `value` | `float` | Slot value with scale factor applied; `NaN` where RiverWare outputs `NaN` |
| `location_id` | `str` | `"{prefix}-{object_name}"` (default prefix `"crmms"`) |
| `member` | `str` | ESP trace number as string (e.g. `"2"` … `"33"`) |

## Usage

### Postprocessing only (in-process)

```python
from pathlib import Path
from riverware.postprocessing.load_results import run_postprocessing

df = run_postprocessing(
    model_dir=Path(r"C:\FVED\Models\CRMMS-ESP\CRMMS-March2025"),
    configuration_name="crmms_esp_march2025",
    parquet_path=Path(r"C:\FVED\output\crmms_march2025.parquet"),  # optional
)
```

### Full pipeline (CLI)

```powershell
python run_pipeline.py `
  --model-dir          "C:\FVED\Models\CRMMS-ESP\CRMMS-March2025" `
  --configuration-name crmms_esp_march2025 `
  --parquet-path       "C:\FVED\output\crmms_march2025.parquet"
```

### Full pipeline via Prefect SSM

```python
from workflows.riverware.riverware_ssm_run import run_riverware_python_script

run_riverware_python_script(
    script_path=r"C:\FVED\teehr-fved\riverware\run_pipeline.py",
    extra_args=[
        "--model-dir",        r"C:\FVED\Models\CRMMS-ESP\CRMMS-March2025",
        "--configuration-name", "crmms_esp_march2025",
        "--parquet-path",     r"C:\FVED\output\crmms_march2025.parquet",
    ],
)
```

### Run model only (CLI)

```powershell
python execution\run_crmms.py --model-dir "C:\FVED\Models\CRMMS-ESP\CRMMS-March2025"
```

Optional flags: `--mdl-filename`, `--mrm-run-name` (default `Run_CBRFC_Ensemble_Fcst_RFC`), `--riverware-exe`.

## Environment

Managed with [uv](https://github.com/astral-sh/uv). Requires Python 3.11+.

```powershell
uv sync --project "C:\FVED\teehr-fved\riverware" --group dev
```

Core dependencies: `pandas`, `pyarrow`. Dev dependencies: `pytest`, `ipykernel`, `openpyxl`, `matplotlib`.

Register the venv as a Jupyter kernel after first sync:

```powershell
.venv\Scripts\python.exe -m ipykernel install --user --name riverware --display-name "riverware (.venv)"
```

## Tests

```powershell
uv run --project "C:\FVED\teehr-fved\riverware" pytest tests/ -v
```

Tests skip automatically if `C:\FVED\Models\CRMMS-ESP\CRMMS-March2025` is not present.
