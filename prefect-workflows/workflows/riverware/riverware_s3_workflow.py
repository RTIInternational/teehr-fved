import time
import uuid
from pathlib import Path

import botocore.session
from botocore.exceptions import ClientError
from prefect import flow, get_run_logger, task

from workflows.utils.common_utils import initialize_evaluation

AWS_REGION = "us-east-1"
RIVERWARE_INSTANCE_ID = "i-0e66f3a0f2bd8d411"
SSM_DOCUMENT = "AWS-RunPowerShellScript"
POLL_INTERVAL_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 600
PYTHON_EXECUTABLE = "uv run"
S3_BUCKET = "dev-fved-riverware-rti-use1"
DEFAULT_TEMP_DIR_PATH = "/data/temp-spark"


def _powershell_quote(value: str) -> str:
    """Wrap a value in single quotes for safe PowerShell argument passing."""
    return "'" + value.replace("'", "''") + "'"


@task(retries=0)
def upload_input_to_s3(run_id: str, bucket: str) -> str:
    """Upload a prototype input file to S3 and return the input prefix URI.

    Uploads a small plaintext file to ``runs/{run_id}/input/input.txt``.
    Long-term this task will be replaced with TEEHR hydrologic data export.

    Parameters
    ----------
    run_id:
        UUID string identifying this specific flow run.
    bucket:
        S3 bucket name.

    Returns
    -------
    str
        Full S3 URI of the input prefix, e.g. ``s3://bucket/runs/{run_id}/input``.
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)

    key = f"runs/{run_id}/input/input.txt"
    body = f"Prototype TEEHR input - run {run_id}\n"

    log.info(f"Uploading input to s3://{bucket}/{key}")
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    log.info("Input upload complete.")

    return f"s3://{bucket}/runs/{run_id}/input"


@task(retries=0)
def run_ssm_script_with_s3(
    script_path: str,
    bucket: str,
    run_id: str,
    model_s3_uri: str,
    configuration_name: str,
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> dict:
    """Send an SSM RunPowerShellScript command that passes required CLI args to the script.

    Parameters
    ----------
    script_path:
        Full Windows path of the Python script on the EC2 instance.
    bucket:
        S3 bucket name for data exchange.
    run_id:
        UUID identifying this Prefect flow run. The EC2 script constructs
        ``runs/{run_id}/input`` and ``runs/{run_id}/output`` paths internally.
    model_s3_uri:
        Full S3 URI to the CRMMS model zip, e.g.,
        ``s3://bucket/models/crmms-esp/2026/10/CRMMS-ESP.zip``.
        The EC2 script will download and extract this to a local working directory.
    configuration_name:
        Label written by the EC2 script to the ``configuration_name`` column.
    python_executable:
        Python runner to invoke. Defaults to ``uv run``. Use ``py`` or a full
        venv path if uv is not available.
    command_timeout_seconds:
        How long SSM will wait for the command to complete before timing out.
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    ssm = session.create_client("ssm", region_name=AWS_REGION)

    command = (
        f'& {python_executable} "{script_path}"'
        f" --bucket {_powershell_quote(bucket)}"
        f" --run-id {_powershell_quote(run_id)}"
        f" --model-s3-uri {_powershell_quote(model_s3_uri)}"
        f" --configuration-name {_powershell_quote(configuration_name)}"
    )
    log.info(f"Sending SSM command to {RIVERWARE_INSTANCE_ID}: {command}")

    send_response = ssm.send_command(
        InstanceIds=[RIVERWARE_INSTANCE_ID],
        DocumentName=SSM_DOCUMENT,
        Parameters={"commands": [command]},
        TimeoutSeconds=command_timeout_seconds,
        Comment=f"Prefect S3 workflow: {script_path[:80]}",
    )

    command_id = send_response["Command"]["CommandId"]
    log.info(f"SSM command submitted. CommandId: {command_id}")

    terminal_states = {
        "Success",
        "Failed",
        "Cancelled",
        "TimedOut",
        "Undeliverable",
        "Terminated",
    }
    elapsed = 0
    poll_timeout = command_timeout_seconds + 60
    while elapsed < poll_timeout:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        try:
            result = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=RIVERWARE_INSTANCE_ID,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvocationDoesNotExist":
                log.debug("Invocation not yet registered, continuing to poll...")
                continue
            raise

        status = result.get("StatusDetails", result.get("Status", "Unknown"))
        log.info(f"SSM command status: {status} (elapsed: {elapsed}s)")

        if status in terminal_states:
            stdout = result.get("StandardOutputContent", "")
            stderr = result.get("StandardErrorContent", "")
            response_code = result.get("ResponseCode", -1)
            if stdout:
                log.info(f"stdout:\n{stdout}")
            if stderr:
                log.warning(f"stderr:\n{stderr}")

            if status != "Success":
                raise RuntimeError(
                    f"SSM command {command_id} finished with status '{status}'\n{stderr}"
                )
            if stderr:
                raise RuntimeError(
                    f"SSM command {command_id} produced error output:\n{stderr}"
                )
            if response_code != 0:
                raise RuntimeError(
                    f"SSM command {command_id} exited with code {response_code}\n{stderr}"
                )
            return result

    raise TimeoutError(
        f"SSM command {command_id} did not complete within {poll_timeout}s"
    )


@flow
def run_riverware_s3_workflow(
    configuration_name: str,
    script_path: str,
    model_s3_uri: str | None = None,
    model_year: int | None = None,
    model_month: int | None = None,
    temp_dir_path: str = DEFAULT_TEMP_DIR_PATH,
    start_spark_cluster: bool = True,
    bucket: str = S3_BUCKET,
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> None:
    """Upload inputs to S3, run an EC2 script via SSM, then load output parquet.

    A unique run UUID is generated for each invocation. Input data is uploaded
    to ``s3://{bucket}/runs/{run_id}/input/``. The EC2 script receives the
    generated ``--run-id`` plus the configured ``--bucket``, ``--model-s3-uri``,
    and ``--configuration-name`` CLI arguments. After the script completes,
    Prefect loads ``s3://{bucket}/runs/{run_id}/output/crmms_output.parquet``
    into the TEEHR warehouse ``secondary_timeseries`` table.

    Parameters
    ----------
    configuration_name:
        Label that the EC2 script writes to the ``configuration_name`` column.
    script_path:
        Full Windows path of the Python script to execute on the EC2 instance
        (e.g. ``C:\\FVED\\Scripts\\riverware_s3_reader.py``).
    model_s3_uri:
        Full S3 URI to the CRMMS model zip, e.g.,
        ``s3://bucket/models/crmms-esp/2026/10/CRMMS-ESP.zip``.
        If provided, ``model_year`` and ``model_month`` are ignored.
        If not provided, ``model_year`` and ``model_month`` must be supplied.
    model_year:
        4-digit year of the model (e.g., 2026). Used to construct S3 URI if
        ``model_s3_uri`` is not provided. Ignored if ``model_s3_uri`` is given.
    model_month:
        Month of the model as an integer 1-12 (e.g., 10 for October).
        Used to construct S3 URI if ``model_s3_uri`` is not provided.
        Ignored if ``model_s3_uri`` is given.
    temp_dir_path:
        Temporary working directory for the TEEHR evaluation used to load the
        CRMMS parquet into the warehouse.
    start_spark_cluster:
        Whether to start a Spark cluster for the remote evaluation load.
    bucket:
        S3 bucket name for data exchange. Defaults to ``dev-fved-riverware-rti-use1``.
    python_executable:
        Python runner to invoke. Defaults to ``uv run`` (uses uv with PEP 723
        inline dependency metadata). Override with ``py`` or a full venv path
        (e.g. ``C:\\venvs\\myenv\\Scripts\\python.exe``) if uv is not available.
    command_timeout_seconds:
        How long (in seconds) SSM will wait for the command to complete.
    """
    log = get_run_logger()

    # Resolve model S3 URI: either use provided URI or construct from year/month
    if model_s3_uri is None:
        if model_year is None or model_month is None:
            raise ValueError(
                "Either model_s3_uri must be provided, or both model_year and model_month "
                "must be supplied."
            )
        # Construct S3 URI from year/month: s3://bucket/models/crmms-esp/YYYY/MM/CRMMS-ESP.zip
        model_s3_uri = f"s3://{bucket}/models/crmms-esp/{model_year:04d}/{model_month:02d}/CRMMS-ESP.zip"
        log.info(f"Constructed model S3 URI from year/month: {model_s3_uri}")
    else:
        log.info(f"Using provided model S3 URI: {model_s3_uri}")

    run_id = str(uuid.uuid4())
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)
    local_dir = Path(temp_dir_path) / run_id / "output"
    local_path = local_dir / "crmms_output.parquet"
    s3_key = f"runs/{run_id}/output/crmms_output.parquet"

    log.info(f"Starting S3 workflow. run_id={run_id}, bucket={bucket}")

    upload_input_to_s3(run_id=run_id, bucket=bucket)

    run_ssm_script_with_s3(
        script_path=script_path,
        bucket=bucket,
        run_id=run_id,
        model_s3_uri=model_s3_uri,
        configuration_name=configuration_name,
        python_executable=python_executable,
        command_timeout_seconds=command_timeout_seconds,
    )

    log.info(f"Downloading s3://{bucket}/{s3_key} to {local_path}")
    local_dir.mkdir(parents=True, exist_ok=True)

    response = s3.get_object(Bucket=bucket, Key=s3_key)
    with open(local_path, "wb") as f:
        f.write(response["Body"].read())

    ev = initialize_evaluation(
        temp_dir_path=Path(temp_dir_path),
        start_spark_cluster=start_spark_cluster,
        update_configs={
            "spark.sql.shuffle.partitions": "4",
        },
    )

    try:
        log.info(f"Loading local parquet into secondary_timeseries from {local_path}")
        ev.secondary_timeseries.load_parquet(local_path)
    finally:
        ev.spark.stop()
        if local_path.exists():
            local_path.unlink()
        if local_dir.exists() and not any(local_dir.iterdir()):
            local_dir.rmdir()
        run_dir = local_dir.parent
        if run_dir.exists() and not any(run_dir.iterdir()):
            run_dir.rmdir()

    log.info(f"S3 workflow completed successfully. run_id={run_id}")
