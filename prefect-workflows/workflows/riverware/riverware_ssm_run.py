import logging
import time

import botocore.session
from botocore.exceptions import ClientError
from prefect import flow, get_run_logger, task

logger = logging.getLogger(__name__)

AWS_REGION = "us-east-1"
RIVERWARE_INSTANCE_ID = "i-0e66f3a0f2bd8d411"
SSM_DOCUMENT = "AWS-RunPowerShellScript"
POLL_INTERVAL_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 600
# Python Launcher (py.exe) is always on the SYSTEM PATH on Windows;
# override with a full path (e.g. C:\Python312\python.exe) if needed.
PYTHON_EXECUTABLE = "py"


@task(
    retries=0,
)
def run_ssm_python_script(
    script_path: str,
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> dict:
    """Send an SSM RunPowerShellScript command to run a Python script and wait for it to finish."""
    log = get_run_logger()
    session = botocore.session.get_session()
    ssm = session.create_client("ssm", region_name=AWS_REGION)

    command = f'& "{python_executable}" "{script_path}"'
    log.info(f"Sending SSM command to {RIVERWARE_INSTANCE_ID}: {command}")

    send_response = ssm.send_command(
        InstanceIds=[RIVERWARE_INSTANCE_ID],
        DocumentName=SSM_DOCUMENT,
        Parameters={"commands": [command]},
        TimeoutSeconds=command_timeout_seconds,
        Comment=f"Prefect: {command[:100]}",
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
            if stdout:
                log.info(f"stdout:\n{stdout}")
            if stderr:
                log.warning(f"stderr:\n{stderr}")
            if status != "Success":
                raise RuntimeError(
                    f"SSM command {command_id} finished with status '{status}'.\n"
                    f"stderr: {stderr}"
                )
            return result

    raise TimeoutError(
        f"SSM command {command_id} did not complete within {poll_timeout}s"
    )


@flow
def run_riverware_python_script(
    script_path: str,
    python_executable: str = PYTHON_EXECUTABLE,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> None:
    """Run a Python script on the RiverWare Windows EC2 instance via AWS SSM.

    Parameters
    ----------
    script_path:
        Full Windows path of the Python script to execute on the instance
        (e.g. ``C:\\FVED\\Scripts\\my_script.py``).
    python_executable:
        Python executable to invoke. Defaults to ``py`` (Windows Python Launcher).
        Override with a full path if ``py`` is not available
        (e.g. ``C:\\Python312\\python.exe``).
    command_timeout_seconds:
        How long (in seconds) SSM will wait for the command to complete before timing out.
    """
    log = get_run_logger()
    log.info(f"Targeting EC2 instance {RIVERWARE_INSTANCE_ID} (region: {AWS_REGION})")

    run_ssm_python_script(
        script_path=script_path,
        python_executable=python_executable,
        command_timeout_seconds=command_timeout_seconds,
    )
    log.info(f"RiverWare Python script '{script_path}' completed successfully.")
