import time
import uuid

import botocore.session
from botocore.exceptions import ClientError
from prefect import flow, get_run_logger, task

AWS_REGION = "us-east-1"
RIVERWARE_INSTANCE_ID = "i-0e66f3a0f2bd8d411"
SSM_DOCUMENT = "AWS-RunPowerShellScript"
POLL_INTERVAL_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 600
PYTHON_EXECUTABLE = "uv run"
S3_BUCKET = "dev-fved-riverware-rti-use1"


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
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> dict:
    """Send an SSM RunPowerShellScript command that passes the bucket and run ID to the script.

    Parameters
    ----------
    script_path:
        Full Windows path of the Python script on the EC2 instance.
    bucket:
        S3 bucket name for data exchange.
    run_id:
        UUID identifying this Prefect flow run. The EC2 script constructs
        ``runs/{run_id}/input`` and ``runs/{run_id}/output`` paths internally.
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
        f'& {python_executable} "{script_path}" --bucket {bucket} --run-id {run_id}'
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


@task(retries=0)
def validate_s3_output(run_id: str, bucket: str) -> None:
    """Verify that the EC2 script wrote at least one file to the output prefix.

    Lists keys under ``runs/{run_id}/output/`` and raises if none are found.

    Parameters
    ----------
    run_id:
        UUID string identifying this specific flow run.
    bucket:
        S3 bucket name.
    """
    log = get_run_logger()
    session = botocore.session.get_session()
    s3 = session.create_client("s3", region_name=AWS_REGION)

    prefix = f"runs/{run_id}/output/"
    log.info(f"Validating outputs at s3://{bucket}/{prefix}")

    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    contents = response.get("Contents", [])

    if not contents:
        raise RuntimeError(
            f"No output files found at s3://{bucket}/{prefix} after SSM command completed."
        )

    for obj in contents:
        log.info(f"Output key: {obj['Key']} ({obj['Size']} bytes)")
    log.info(f"Output validation passed: {len(contents)} file(s) found.")


@flow
def run_riverware_s3_workflow(
    script_path: str,
    bucket: str = S3_BUCKET,
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> None:
    """Upload inputs to S3, run an EC2 script via SSM, then validate outputs.

    A unique run UUID is generated for each invocation. Input data is uploaded
    to ``s3://{bucket}/runs/{run_id}/input/`` and the full S3 prefix URIs are
    passed to the EC2 script as ``--input-prefix`` and ``--output-prefix`` CLI
    arguments. After the script completes, Prefect verifies that at least one
    output file was written to ``s3://{bucket}/runs/{run_id}/output/``.

    Parameters
    ----------
    script_path:
        Full Windows path of the Python script to execute on the EC2 instance
        (e.g. ``C:\\FVED\\Scripts\\riverware_s3_reader.py``).
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
    run_id = str(uuid.uuid4())
    log.info(f"Starting S3 workflow. run_id={run_id}, bucket={bucket}")

    upload_input_to_s3(run_id=run_id, bucket=bucket)

    run_ssm_script_with_s3(
        script_path=script_path,
        bucket=bucket,
        run_id=run_id,
        python_executable=python_executable,
        command_timeout_seconds=command_timeout_seconds,
    )

    validate_s3_output(run_id=run_id, bucket=bucket)
    log.info(f"S3 workflow completed successfully. run_id={run_id}")
