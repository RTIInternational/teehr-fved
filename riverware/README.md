# RiverWare / CRMMS

Python package for running the CRMMS RiverWare model and postprocessing its outputs. Scripts are deployed to the RiverWare Windows EC2 instance and invoked remotely via AWS SSM from the Prefect workflow in [`prefect-workflows/workflows/riverware/`](../prefect-workflows/workflows/riverware/).

## Folder Structure

```
riverware/
├── run_pipeline.py              # ← Prefect entrypoint: execute model + postprocess → Parquet → S3
│
├── execution/
│   └── run_crmms.py             # Generate .rcl, launch RiverWare in batch mode, tail run.log
│
├── postprocessing/
│   ├── extract_outputs.py       # Parse .rdf files → TEEHR-schema DataFrame (variable mapping, metric conversion, NaN check)
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
2. **Postprocessing** — `run_postprocessing()` reads `rdfOutput/*.rdf` and `run.log`, returns a [TEEHR secondary timeseries](https://github.com/RTIInternational/teehr) schema DataFrame, and optionally writes a Parquet file. It:
   - keeps only slots listed in `CRMMS_VARIABLE_MAP` (plus any `variable_name_map` overrides); other slots are skipped,
   - raises `ValueError` if any value is `NaN` (TEEHR validation rejects them),
   - converts English units to metric and raises `ValueError` for units with no known conversion.

`run_pipeline.py` orchestrates the steps and is the single script invoked by Prefect:

1. Download inputs from `s3://<bucket>/runs/<run-id>/input/` — **not yet implemented** (stubbed with a TODO until the input format is defined).
2. Execute the model.
3. Postprocess the RDF outputs.
4. Upload the Parquet to `s3://<bucket>/runs/<run-id>/output/crmms_output.parquet`.

## Output Schema

`run_postprocessing()` returns a `pandas.DataFrame` with these columns:

| Column | Type | Description |
|---|---|---|
| `reference_time` | `datetime64[us, UTC]` | Model init date (from `run.log` `Begin date`) |
| `value_time` | `datetime64[us, UTC]` | Simulation timestep (RiverWare 24:00 → next-day UTC) |
| `configuration_name` | `str` | Caller-supplied label (e.g. `"crmms_esp_march2025"`) |
| `unit_name` | `str` | Metric unit after conversion: `"m"`, `"m^3"`, `"m^3/s"`, or `"GWH"` (energy, unconverted) |
| `variable_name` | `str` | TEEHR variable name from `CRMMS_VARIABLE_MAP` (e.g. `"poolelevation_monthly_inst"`, `"inflow_monthly_mean"`, `"energy_monthly_sum"`). Slots not in the map are skipped. Add or override entries with `variable_name_map=`. |
| `value` | `float` | Slot value converted to metric units (ft → m, acre-ft → m³, cfs → m³/s, acre-ft/month → mean m³/s over the month). Never `NaN`. |
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
  --bucket             dev-fved-riverware-rti-use1 `
  --run-id             <prefect-flow-run-uuid> `
  --model-dir          "C:\FVED\Models\CRMMS-ESP\CRMMS-March2025" `
  --configuration-name crmms_esp_march2025
```

Required: `--bucket`, `--run-id`, `--model-dir`, `--configuration-name`.
Optional: `--mdl-filename` (auto-detected if omitted), `--mrm-run-name` (default `Run_CBRFC_Ensemble_Fcst_RFC`), `--riverware-exe`.

The Parquet is written to a temporary directory and uploaded to S3; it is not kept locally. Requires AWS credentials available to `boto3` on the machine.

### Full pipeline via Prefect SSM

```python
from workflows.riverware.riverware_ssm_run import run_riverware_python_script

run_riverware_python_script(
    script_path=r"C:\FVED\teehr-fved\riverware\run_pipeline.py",
)
```

> **Note:** `run_riverware_python_script` currently runs the script with no command-line arguments, but `run_pipeline.py` requires `--bucket`, `--run-id`, `--model-dir`, and `--configuration-name`. The flow needs an argument-passing option before the full pipeline can be run through Prefect.

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

Core dependencies: `pandas`, `pyarrow`, `boto3`. Dev dependencies: `pytest`, `ipykernel`, `openpyxl`, `matplotlib`.

Register the venv as a Jupyter kernel after first sync:

```powershell
.venv\Scripts\python.exe -m ipykernel install --user --name riverware --display-name "riverware (.venv)"
```

## Tests

```powershell
uv run --project "C:\FVED\teehr-fved\riverware" pytest tests/ -v
```

Tests skip automatically if `C:\FVED\Models\CRMMS-ESP\CRMMS-March2025` is not present.
