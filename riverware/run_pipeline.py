"""End-to-end CRMMS pipeline: execute RiverWare model, then postprocess outputs to Parquet."""

import argparse
import sys
from pathlib import Path

# Allow running as a standalone script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riverware.execution.run_crmms import (
    _DEFAULT_MRM_RUN_NAME,
    _DEFAULT_RIVERWARE_EXE,
    run_crmms,
)
from riverware.postprocessing.load_results import run_postprocessing


def run_pipeline(
    model_dir: Path,
    configuration_name: str,
    parquet_path: Path,
    mdl_filename: str | None = None,
    mrm_run_name: str = _DEFAULT_MRM_RUN_NAME,
    riverware_exe: Path = _DEFAULT_RIVERWARE_EXE,
) -> Path:
    """Execute CRMMS and postprocess RDF outputs to a Parquet file. Returns the parquet path."""
    model_dir = Path(model_dir)
    parquet_path = Path(parquet_path)

    print("=== Step 1: Execute CRMMS model ===")
    run_crmms(
        model_dir=model_dir,
        mdl_filename=mdl_filename,
        mrm_run_name=mrm_run_name,
        riverware_exe=Path(riverware_exe),
    )

    print("\n=== Step 2: Postprocess RDF outputs ===")
    df = run_postprocessing(
        model_dir=model_dir,
        configuration_name=configuration_name,
        parquet_path=parquet_path,
    )
    print(f"Wrote {len(df):,} rows → {parquet_path}")
    return parquet_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run CRMMS RiverWare model and postprocess outputs to Parquet."
    )
    parser.add_argument("--model-dir", required=True, type=Path,
                        help="Directory containing 'RW Files/', 'rdfOutput/', and 'run.log'.")
    parser.add_argument("--configuration-name", required=True,
                        help="Label written to the configuration_name column (e.g. crmms_esp_march2025).")
    parser.add_argument("--parquet-path", required=True, type=Path,
                        help="Destination path for the output Parquet file.")
    parser.add_argument("--mdl-filename",
                        help="Specific .mdl filename inside 'RW Files/'. Auto-detected if omitted.")
    parser.add_argument("--mrm-run-name", default=_DEFAULT_MRM_RUN_NAME,
                        help=f"MRM run name in the RCL script (default: {_DEFAULT_MRM_RUN_NAME}).")
    parser.add_argument("--riverware-exe", type=Path, default=_DEFAULT_RIVERWARE_EXE,
                        help=f"Path to RiverWare.exe (default: {_DEFAULT_RIVERWARE_EXE}).")

    args = parser.parse_args()
    run_pipeline(
        model_dir=args.model_dir,
        configuration_name=args.configuration_name,
        parquet_path=args.parquet_path,
        mdl_filename=args.mdl_filename,
        mrm_run_name=args.mrm_run_name,
        riverware_exe=args.riverware_exe,
    )
