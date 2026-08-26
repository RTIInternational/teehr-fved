"""End-to-end CRMMS pipeline: execute RiverWare model, postprocess outputs, upload Parquet to S3."""

import argparse
import sys
import tempfile
from pathlib import Path

import boto3

# Allow running as a standalone script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riverware.execution.run_crmms import (
    _DEFAULT_MRM_RUN_NAME,
    _DEFAULT_RIVERWARE_EXE,
    run_crmms,
)
from riverware.postprocessing.load_results import run_postprocessing


def download_inputs(s3_client, bucket: str, prefix: str) -> list[tuple[str, bytes]]:
    """Download all objects under prefix. Returns list of (key, data)."""
    paginator = s3_client.get_paginator("list_objects_v2")
    results = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix + "/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            data = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
            print(f"  Downloaded: s3://{bucket}/{key} ({len(data):,} bytes)")
            results.append((key, data))
    return results


def upload_file(s3_client, local_path: Path, bucket: str, key: str) -> None:
    s3_client.upload_file(str(local_path), bucket, key)
    print(f"  Uploaded:   s3://{bucket}/{key}")


def run_pipeline(
    model_dir: Path,
    configuration_name: str,
    bucket: str,
    run_id: str,
    mdl_filename: str | None = None,
    mrm_run_name: str = _DEFAULT_MRM_RUN_NAME,
    riverware_exe: Path = _DEFAULT_RIVERWARE_EXE,
) -> None:
    """Execute CRMMS, postprocess RDF outputs, and upload the Parquet result to S3."""
    model_dir = Path(model_dir)
    in_prefix = f"runs/{run_id}/input"
    out_prefix = f"runs/{run_id}/output"

    s3 = boto3.client("s3")

    print(f"=== Step 1: Download inputs from s3://{bucket}/{in_prefix}/ ===")
    inputs = download_inputs(s3, bucket, in_prefix)
    if not inputs:
        raise RuntimeError(f"No input files found at s3://{bucket}/{in_prefix}/")
    # TODO: process input files into model staging area once input format is defined

    print("\n=== Step 2: Execute CRMMS model ===")
    run_crmms(
        model_dir=model_dir,
        mdl_filename=mdl_filename,
        mrm_run_name=mrm_run_name,
        riverware_exe=Path(riverware_exe),
    )

    print("\n=== Step 3: Postprocess RDF outputs ===")
    with tempfile.TemporaryDirectory() as tmp:
        parquet_path = Path(tmp) / "crmms_output.parquet"
        df = run_postprocessing(
            model_dir=model_dir,
            configuration_name=configuration_name,
            parquet_path=parquet_path,
        )
        print(f"  Postprocessed {len(df):,} rows")

        print(f"\n=== Step 4: Upload output to s3://{bucket}/{out_prefix}/ ===")
        upload_file(s3, parquet_path, bucket, f"{out_prefix}/crmms_output.parquet")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run CRMMS RiverWare model and postprocess outputs to S3."
    )
    parser.add_argument("--bucket", required=True,
                        help="S3 bucket name (e.g. dev-fved-riverware-rti-use1).")
    parser.add_argument("--run-id", required=True,
                        help="UUID identifying this Prefect flow run.")
    parser.add_argument("--model-dir", required=True, type=Path,
                        help="Local directory containing 'RW Files/', 'rdfOutput/', and 'run.log'.")
    parser.add_argument("--configuration-name", required=True,
                        help="Label written to the configuration_name column (e.g. crmms_esp_march2025).")
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
        bucket=args.bucket,
        run_id=args.run_id,
        mdl_filename=args.mdl_filename,
        mrm_run_name=args.mrm_run_name,
        riverware_exe=args.riverware_exe,
    )
