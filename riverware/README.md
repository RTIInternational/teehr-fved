# RiverWare / CRMMS

Python scripts for executing the Colorado River Management Model System (CRMMS) RiverWare model. These scripts are deployed to the RiverWare Windows EC2 instance and invoked remotely via AWS SSM from the Prefect workflow in [`prefect-workflows/workflows/riverware/`](../prefect-workflows/workflows/riverware/).

## Folder Structure

```
riverware/
├── preprocessing/           # Prepare input data before running the model
│   └── prepare_inflows.py       # Fetch/format streamflow and NWM inflow inputs
│
├── execution/               # Launch the RiverWare model
│   └── run_crmms.py             # Invoke RiverWare via CLI or RCL script
│
├── postprocessing/          # Handle model outputs
│   ├── extract_outputs.py       # Parse RiverWare output files (CSV, RDF, etc.)
│   └── load_results.py          # Push results to downstream storage (S3, DB, etc.)
│
└── utils/                   # Shared helpers used across all stages
    └── riverware_utils.py       # File I/O, date utilities, RiverWare-specific helpers
```

## Workflow

1. **Preprocessing** — Input data is fetched and formatted into the files/slots expected by the RiverWare model.
2. **Execution** — The CRMMS RiverWare model is invoked. The run is triggered remotely by the Prefect SSM workflow.
3. **Postprocessing** — Model output files are parsed and results are loaded to downstream storage for analysis.

## Remote Execution

Scripts in this folder are executed on the RiverWare Windows EC2 instance via the `run_riverware_python_script` Prefect flow:

```python
from workflows.riverware.riverware_ssm_run import run_riverware_python_script

run_riverware_python_script(script_path=r"C:\FVED\riverware\execution\run_crmms.py")
```
