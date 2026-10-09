"""Check for CRMMS model updates and stage to S3 if found."""

import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import botocore.session
import requests
from botocore.exceptions import ClientError
from prefect import flow, get_run_logger, task
from prefect.blocks.system import Secret

from workflows.riverware.riverware_s3_workflow import run_riverware_s3_workflow

AWS_REGION = "us-east-1"
USBR_MODEL_URL = "https://www.usbr.gov/lc/region/g4000/CRMMS-ESP.zip"
S3_BUCKET = "dev-fved-riverware-rti-use1"
S3_MODELS_PREFIX = "models/crmms-esp"
S3_LATEST_KEY = f"{S3_MODELS_PREFIX}/latest.json"
HTTP_TIMEOUT = (10, 300)


@task(retries=0)
def get_latest_manifest(bucket: str) -> dict | None:
    """Read the latest.json manifest from S3 to check last processed month.

    Parameters
    ----------
    bucket:
        S3 bucket name.

    Returns
    -------
    dict or None
        Manifest with keys: model_month, sha256, staged_s3_uri, fetched_at.
        Returns None if manifest does not exist.
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)

    try:
        log.info(f"Reading latest manifest from s3://{bucket}/{S3_LATEST_KEY}")
        response = s3.get_object(Bucket=bucket, Key=S3_LATEST_KEY)
        manifest = json.loads(response["Body"].read().decode("utf-8"))
        log.info(f"Latest manifest found: model_month={manifest.get('model_month')}")
        return manifest
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            log.info("No latest manifest found; first model fetch.")
            return None
        raise


@task(retries=0)
def download_and_detect_model_month(
    url: str, password_format: str
) -> tuple[bytes, str, str]:
    """Download the CRMMS model zip and detect its month from the root folder.

    Downloads the zip (which is password-protected) and determines the actual model
    version by examining the root folder name in the archive (e.g., "CRMMS_July2026").
    Returns the bytes and the detected month in YYYY-MM format.

    Parameters
    ----------
    url:
        Full URL to the zip file.
    password_format:
        Python strftime format string for the download password (from Prefect secrets).

    Returns
    -------
    tuple
        (zip_bytes, sha256_hex, model_month_YYYY-MM)
        where model_month_YYYY-MM is the detected month as a string like "2026-09".

    Raises
    ------
    ValueError
        If the zip cannot be extracted or the root folder cannot be parsed.
    """
    log = get_run_logger()
    log.info(f"Downloading model from {url}")

    response = requests.get(url, timeout=HTTP_TIMEOUT, stream=False)
    response.raise_for_status()

    zip_bytes = response.content
    sha256_hex = hashlib.sha256(zip_bytes).hexdigest()
    log.info(f"Downloaded {len(zip_bytes):,} bytes, sha256={sha256_hex}")

    # Try to extract with passwords for current and previous months
    now = datetime.now(timezone.utc)
    max_attempts = 3

    for attempt in range(max_attempts):
        test_date = now - timedelta(days=30 * attempt)
        password = test_date.strftime(password_format)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Get list of files and try to read the first one to validate password
                file_list = zf.namelist()
                if not file_list:
                    raise ValueError("Zip file is empty")

                # Try reading the first file with the password to validate it works
                first_file = file_list[0]
                _ = zf.read(first_file, pwd=password.encode())

                # Extract root folder name (e.g., "CRMMS_July2026")
                # The root is typically the first path component before any '/'
                root_folder = file_list[0].split("/")[0]

                # Parse root folder name: "CRMMS_MonthYear" -> month and year
                # Expected format: CRMMS_July2026, CRMMS_October2026, etc.
                if not root_folder.startswith("CRMMS_"):
                    raise ValueError(
                        f"Unexpected root folder format: {root_folder}. "
                        "Expected 'CRMMS_MonthYear'"
                    )

                month_year_str = root_folder[6:]  # Remove "CRMMS_" prefix

                # Parse the month year string back to datetime
                # The format comes from password_format, but we'll try common formats
                try:
                    # Try parsing with common month formats
                    model_date = datetime.strptime(month_year_str, "%B%Y").astimezone()
                except ValueError:
                    raise ValueError(
                        f"Could not parse model version from folder: {root_folder}. "
                        f"Expected format like 'CRMMS_July2026'"
                    )

                model_month = model_date.strftime("%Y-%m")
                log.info(
                    f"Successfully extracted zip with password '{password}' "
                    f"(detected model version from folder '{root_folder}': {model_month})"
                )
                return zip_bytes, sha256_hex, model_month
        except RuntimeError as e:
            if (
                "Bad password" in str(e)
                or "Bad CRC" in str(e)
                or "encrypted" in str(e).lower()
            ):
                log.warning(
                    f"Attempt {attempt + 1}/{max_attempts}: password '{password}' failed - {e}"
                )
                continue
            raise

    raise ValueError(
        f"Failed to extract zip with passwords for the last {max_attempts} months. "
        "The model may not be available yet."
    )


@task(retries=0)
def upload_model_to_s3(
    zip_bytes: bytes, model_month: str, sha256_hex: str, bucket: str
) -> str:
    """Upload the zip to S3 under models/crmms-esp/YYYY/MM/ layout.

    Parameters
    ----------
    zip_bytes:
        The downloaded zip content.
    model_month:
        Month in YYYY-MM format.
    sha256_hex:
        SHA256 hash of the zip.
    bucket:
        S3 bucket name.

    Returns
    -------
    str
        Full S3 URI of the staged zip, e.g., s3://bucket/models/crmms-esp/2026/10/CRMMS-ESP.zip
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)

    # Parse YYYY-MM into year and month
    year, month = model_month.split("-")
    s3_key = f"{S3_MODELS_PREFIX}/{year}/{month}/CRMMS-ESP.zip"
    s3_uri = f"s3://{bucket}/{s3_key}"

    log.info(f"Uploading model to {s3_uri}")
    s3.put_object(Bucket=bucket, Key=s3_key, Body=zip_bytes)
    log.info("Model upload complete.")

    return s3_uri


@task(retries=0)
def write_latest_manifest(
    bucket: str, model_month: str, sha256_hex: str, s3_uri: str
) -> dict:
    """Write or update latest.json manifest in S3.

    Parameters
    ----------
    bucket:
        S3 bucket name.
    model_month:
        Month in YYYY-MM format.
    sha256_hex:
        SHA256 hash of the staged zip.
    s3_uri:
        Full S3 URI of the staged zip.

    Returns
    -------
    dict
        The manifest that was written.
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)

    manifest = {
        "model_month": model_month,
        "sha256": sha256_hex,
        "staged_s3_uri": s3_uri,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"Writing manifest to s3://{bucket}/{S3_LATEST_KEY}")
    s3.put_object(Bucket=bucket, Key=S3_LATEST_KEY, Body=json.dumps(manifest, indent=2))
    log.info("Manifest write complete.")

    return manifest


@flow
def check_crmms_model_update(
    bucket: str = S3_BUCKET,
    configuration_name: str = "crmms_esp",
    source_url: str = USBR_MODEL_URL,
    script_path: str = r"C:\FVED\teehr-fved\riverware\run_pipeline.py",
    temp_dir_path: str = "/data/temp-spark",
) -> str | None:
    """Check for new CRMMS model, stage to S3, and trigger RiverWare run if found.

    Parameters
    ----------
    bucket:
        S3 bucket name for data exchange. Defaults to dev-fved-riverware-rti-use1.
    configuration_name:
        Label written by the EC2 script to the configuration_name column.
        Defaults to "crmms_esp".
    source_url:
        URL to download the CRMMS model zip from. Defaults to USBR endpoint.
    script_path:
        Full Windows path of the Python script on the EC2 instance.
    temp_dir_path:
        Temporary working directory for the TEEHR evaluation.

    Returns
    -------
    str or None
        The S3 URI of the staged model if a new one was found and processed.
        None if the current model was already up-to-date.
    """
    log = get_run_logger()
    log.info("Starting CRMMS model update check...")

    # Get last processed manifest
    latest = get_latest_manifest(bucket=bucket)

    # Download model and detect month from root folder
    log.info(f"Downloading model from {source_url} and detecting month...")

    # Retrieve password format from Prefect secrets (required)
    password_format = Secret.load("crmms-esp-password-format").get()

    zip_bytes, sha256_hex, model_month = download_and_detect_model_month(
        url=source_url,
        password_format=password_format,
    )

    # Check if this exact model is already staged (same month and SHA256)
    if (
        latest
        and latest.get("model_month") == model_month
        and latest.get("sha256") == sha256_hex
    ):
        log.info(
            f"Model {model_month} with matching SHA256 already staged. "
            f"Skipping upload. Staged URI: {latest.get('staged_s3_uri')}"
        )
        return None

    log.info(f"New or updated model detected: {model_month}. Staging to S3...")

    # New content: upload to S3
    s3_uri = upload_model_to_s3(
        zip_bytes=zip_bytes,
        model_month=model_month,
        sha256_hex=sha256_hex,
        bucket=bucket,
    )

    # Update manifest
    write_latest_manifest(
        bucket=bucket,
        model_month=model_month,
        sha256_hex=sha256_hex,
        s3_uri=s3_uri,
    )

    log.info(f"New model staged: {s3_uri}. Triggering RiverWare run...")

    # Trigger RiverWare run as a subflow
    # Parse model_month (YYYY-MM) into year and month integers
    year_str, month_str = model_month.split("-")
    model_year = int(year_str)
    model_month_int = int(month_str)

    run_riverware_s3_workflow(
        configuration_name=configuration_name,
        script_path=script_path,
        model_year=model_year,
        model_month=model_month_int,
        temp_dir_path=temp_dir_path,
        bucket=bucket,
    )

    log.info(f"CRMMS model update complete. Staged: {s3_uri}")
    return s3_uri
