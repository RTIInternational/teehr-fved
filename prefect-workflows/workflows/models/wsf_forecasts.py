"""Execute Rodeo inference and archive original model outputs, without warehouse loading."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from prefect import flow, get_run_logger, task
from prefect.blocks.system import Secret
from prefect.cache_policies import NO_CACHE
from prefect.context import get_run_context

from workflows.models import wsf_utils as wsf


@task(cache_policy=NO_CACHE)
def prepare_assets(solution: str, uri: str, cache_dir: Path) -> Path:
    return wsf.stage_assets(solution, uri, cache_dir, wsf.s3_client())


@task(cache_policy=NO_CACHE)
def execute_stage(command: list[str], cwd: Path, env: dict, log_path: Path, timeout: int) -> None:
    wsf.run_command(command, cwd, env, log_path, timeout, get_run_logger())


@task(cache_policy=NO_CACHE)
def publish_run(directory: Path, uri: str) -> str:
    return wsf.archive_run(directory, uri, wsf.s3_client())


def model_environment(solution: str, strict: bool) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(wsf.model_directory(solution))
    env["PYTHONUNBUFFERED"] = "1"
    if solution == "rasyidstat_3rd":
        for key in ("CDSAPI_URL", "CDSAPI_KEY"):
            if not env.get(key):
                try:
                    env[key] = Secret.load(key.lower().replace("_", "-")).get()
                except ValueError:
                    pass
        if strict and not Path.home().joinpath(".cdsapirc").is_file():
            if not all(env.get(key) for key in ("CDSAPI_URL", "CDSAPI_KEY")):
                raise ValueError("Full third-place inference requires CDSAPI_URL/CDSAPI_KEY or ~/.cdsapirc")
    return env


@flow(name="wsf-inference", timeout_seconds=10800)
def run_wsf_inference(
    solution: str,
    issue_date: str | None = None,
    sites: list[str] | None = None,
    assets_s3_uri: str | None = None,
    output_s3_uri: str | None = None,
    cache_dir: str = "/data/wsf",
    model_python: str = wsf.MODEL_PYTHON,
    strict_ensemble: bool = True,
    download_timeout_seconds: int = 7200,
    stage_timeout_seconds: int = 1800,
) -> dict:
    logger = get_run_logger()
    context = get_run_context()
    run = context.flow_run
    issue = wsf.resolve_issue_date(issue_date, run.expected_start_time, run.auto_scheduled)
    package_dir = wsf.model_directory(solution)
    selected = wsf.eligible_sites(issue, sites, solution)
    assets_uri = assets_s3_uri or os.getenv("WSF_ASSETS_S3_URI", "").rstrip("/") + f"/{solution}"
    output_uri = output_s3_uri or os.getenv("WSF_OUTPUT_S3_URI", "")
    wsf.s3_location(assets_uri)
    wsf.s3_location(output_uri)
    if not Path(model_python).is_file():
        raise ValueError(f"Shared wsf_py313 interpreter not found: {model_python}")
    if download_timeout_seconds <= 0 or stage_timeout_seconds <= 0:
        raise ValueError("Stage timeouts must be positive")
    env = model_environment(solution, strict_ensemble)
    cache = Path(cache_dir).expanduser().resolve()
    revision = wsf.source_digest()
    attempt = str(uuid4())
    run_dir = cache / "runs" / str(run.id) / attempt
    run_dir.mkdir(parents=True, exist_ok=True)
    destination = f"{output_uri.rstrip('/')}/{solution}/{issue.isoformat()}/{run.id}/{attempt}"
    record = {
        "solution": solution, "issue_date": issue.isoformat(), "sites": selected,
        "flow_run_id": str(run.id), "source_digest": revision,
        "attempt_id": attempt,
        "environment_digest": wsf.file_digest(wsf.INFERENCE_DIR / "uv.lock"),
        "project_digest": wsf.file_digest(wsf.INFERENCE_DIR / "pyproject.toml"),
        "assets_manifest_digest": wsf.file_digest(package_dir / "assets.sha256"),
        "strict_ensemble": strict_ensemble, "units": "KAF", "status": "running",
        "scheduled_start": run.expected_start_time.isoformat() if run.expected_start_time else None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "archive_uri": destination,
    }
    try:
        with wsf.solution_lock(cache, solution):
            assets = prepare_assets(solution, assets_uri, cache)
            root = cache / "work" / revision / issue.isoformat()
            base = root / solution
            base.mkdir(parents=True, exist_ok=True)
            linked_assets = base / "assets"
            if linked_assets.is_symlink():
                if linked_assets.resolve() != assets.resolve():
                    raise ValueError("Working root points to a different asset version")
            elif linked_assets.exists():
                raise ValueError("Working root assets must be a link to the verified cache")
            else:
                linked_assets.symlink_to(assets, target_is_directory=True)
            forecast = run_dir / "forecast.csv"
            forecast.unlink(missing_ok=True)
            stages = ["check-assets", "build", "download"]
            if solution == "rasyidstat_3rd":
                stages.append("preprocess")
            stages.append("predict")
            for stage in stages:
                command = [model_python, "-m", wsf.MODEL_PACKAGES[solution], stage, "--root", str(root)]
                if stage in ("download", "preprocess", "predict"):
                    command.extend(["--issue-date", issue.isoformat()])
                if solution == "rasyidstat_3rd" and strict_ensemble:
                    command.append("--strict")
                if stage == "predict":
                    command.extend(["--out", str(forecast), "--sites", *selected])
                record["stage"] = stage
                execute_stage(
                    command, package_dir, env, run_dir / "logs" / f"{stage}.log",
                    download_timeout_seconds if stage == "download" else stage_timeout_seconds,
                )
            frame = wsf.validate_forecast(forecast, issue, selected, strict_ensemble)
            record.update(status="succeeded", model_versions=sorted(frame.model_version.unique().tolist()))
            record["forecast_digest"] = wsf.file_digest(forecast)
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        (run_dir / "run.json").write_text(json.dumps(record, indent=2))
        try:
            publish_run(run_dir, destination)
        except Exception:
            logger.warning("Failed to archive diagnostics; retained locally at %s", run_dir)
        raise
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run.json").write_text(json.dumps(record, indent=2))
    publish_run(run_dir, destination)
    logger.info("Archived %s forecast rows to %s", len(frame), destination)
    return record