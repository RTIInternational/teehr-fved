import logging
import time

import boto3
from botocore.exceptions import ClientError
from prefect import flow, get_run_logger, task

logger = logging.getLogger(__name__)

AWS_REGION = "us-east-1"
RIVERWARE_NAME_TAG = "fved-riverware-windows-dev"
RIVERWARE_ROLE_TAG = "riverware-windows-dev"
SSM_DOCUMENT = "AWS-RunPowerShellScript"
POLL_INTERVAL_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 600


@task(
    retries=0,
)
def run_ssm_python_script(
    script_path: str,
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> dict:
    """Send an SSM RunPowerShellScript command to run a Python script and wait for it to finish."""
    log = get_run_logger()
    ssm = boto3.client("ssm", region_name=AWS_REGION)

    command = f'python "{script_path}"'
    log.info(
        "Sending SSM command to target tags "
        f"Name={RIVERWARE_NAME_TAG}, fved/role={RIVERWARE_ROLE_TAG}: {command}"
    )

    send_response = ssm.send_command(
        Targets=[
            {"Key": "tag:Name", "Values": [RIVERWARE_NAME_TAG]},
            {"Key": "tag:fved/role", "Values": [RIVERWARE_ROLE_TAG]},
        ],
        DocumentName=SSM_DOCUMENT,
        Parameters={"commands": [command]},
        TimeoutSeconds=command_timeout_seconds,
        Comment=f"Prefect: {command[:100]}",
    )

    target_count = send_response["Command"].get("TargetCount", 0)
    if target_count != 1:
        raise RuntimeError(
            "Expected exactly one SSM target instance for "
            f"Name={RIVERWARE_NAME_TAG}, fved/role={RIVERWARE_ROLE_TAG}; got {target_count}."
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
    target_instance_id = None
    while elapsed < poll_timeout:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        invocations = ssm.list_command_invocations(
            CommandId=command_id,
            Details=False,
        ).get("CommandInvocations", [])
        if not invocations:
            log.debug("Command invocation not yet available, continuing to poll...")
            continue

        invocation = invocations[0]
        target_instance_id = invocation.get("InstanceId")

        try:
            result = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=target_instance_id,
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
    command_timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> None:
    """Run a Python script on the RiverWare Windows EC2 instance via AWS SSM.

    Parameters
    ----------
    script_path:
        Full Windows path of the Python script to execute on the instance
        (e.g. ``C:\\FVED\\Scripts\\my_script.py``).
    command_timeout_seconds:
        How long (in seconds) SSM will wait for the command to complete before timing out.
    """
    log = get_run_logger()
    log.info(
        "Targeting EC2 instance by tags "
        f"Name={RIVERWARE_NAME_TAG}, fved/role={RIVERWARE_ROLE_TAG} (region: {AWS_REGION})"
    )

    run_ssm_python_script(
        script_path=script_path,
        command_timeout_seconds=command_timeout_seconds,
    )
    log.info(f"RiverWare Python script '{script_path}' completed successfully.")
