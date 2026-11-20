"""Contracts and isolated execution for the three Rodeo inference packages."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import csv
import fcntl
import hashlib
import os
from pathlib import Path
import sys
import signal
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import urlparse


INFERENCE_DIR = Path(__file__).resolve().parents[2] / "wsfr_inference"
MODEL_PACKAGES = {
    "oshbocker_1st": "oshbocker_infer",
    "ckua_2nd": "ckua_infer",
    "rasyidstat_3rd": "rasyidstat_infer",
}
MODEL_PYTHON = sys.executable
QUANTILES = (10, 50, 90)


def resolve_issue_date(
    issue_date: str | None,
    scheduled_start: datetime | None = None,
    auto_scheduled: bool = False,
) -> date:
    if issue_date is not None:
        resolved = date.fromisoformat(issue_date)
        if resolved.isoformat() != issue_date:
            raise ValueError("issue_date must use YYYY-MM-DD")
    else:
        if not auto_scheduled or scheduled_start is None:
            raise ValueError("Manual runs require an explicit issue_date (YYYY-MM-DD)")
        if scheduled_start.tzinfo is None:
            raise ValueError("Scheduled timestamp must include a timezone")
        resolved = scheduled_start.astimezone(timezone.utc).date()
        if resolved.day not in (1, 8, 15, 22):
            raise ValueError("Scheduled issue dates must be on the 1st, 8th, 15th or 22nd")
    if not 1 <= resolved.month <= 7:
        raise ValueError("issue_date must be in January through July")
    return resolved


def model_directory(solution: str) -> Path:
    if solution not in MODEL_PACKAGES:
        raise ValueError(f"Unknown solution: {solution}")
    return INFERENCE_DIR / solution


def read_model_sites(solution: str) -> dict[str, dict]:
    relative = "static/raw/metadata.csv" if solution == "rasyidstat_3rd" else "static/metadata.csv"
    with (model_directory(solution) / relative).open(newline="") as handle:
        records = list(csv.DictReader(handle))
    mapping = {}
    for record in records:
        site = record["site_id"]
        if site in mapping:
            raise ValueError(f"Duplicate model site: {site}")
        record["season_start_month"] = int(record["season_start_month"])
        record["season_end_month"] = int(record["season_end_month"])
        mapping[site] = record
    return mapping


def eligible_sites(issue: date, sites: list[str] | None = None, solution: str = "ckua_2nd") -> list[str]:
    mapping = read_model_sites(solution)
    requested = list(mapping) if sites is None else sites
    if not requested or len(requested) != len(set(requested)):
        raise ValueError("sites must be nonempty and unique")
    unknown = set(requested) - mapping.keys()
    if unknown:
        raise ValueError(f"Unknown sites: {sorted(unknown)}")
    eligible = [site for site in requested if issue.month <= mapping[site]["season_end_month"]]
    if sites is not None and len(eligible) != len(requested):
        raise ValueError("Requested sites include a site whose forecast season has ended")
    if not eligible:
        raise ValueError("No eligible sites for this issue date")
    return eligible


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(INFERENCE_DIR.rglob("*")):
        if path.is_file() and not {"__pycache__", ".pytest_cache"}.intersection(path.parts):
            digest.update(path.relative_to(INFERENCE_DIR).as_posix().encode())
            digest.update(file_digest(path).encode())
    return digest.hexdigest()


def manifest_files(manifest: Path) -> dict[str, str]:
    entries = {}
    for line in manifest.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError(f"Unsafe or duplicate manifest entry: {relative}")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"Invalid SHA256 digest for {relative}")
        entries[relative] = digest
    if not entries:
        raise ValueError("Empty asset manifest")
    return entries


def verify_assets(directory: Path, manifest: Path) -> None:
    expected = manifest_files(manifest)
    for relative, digest in expected.items():
        path = directory / relative
        if not path.is_file() or file_digest(path) != digest:
            raise ValueError(f"Missing or changed asset: {relative}")
    present = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if present != set(expected):
        raise ValueError("Asset directory contains unexpected files")


def s3_location(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Expected an s3://bucket/prefix URI")
    return parsed.netloc, parsed.path.lstrip("/").rstrip("/")


def s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("WSF_S3_ENDPOINT_URL") or os.getenv("REMOTE_CATALOG_S3_ENDPOINT") or None,
        config=Config(retries={"max_attempts": 4, "mode": "standard"}, s3={"addressing_style": "path"}),
    )


def stage_assets(solution: str, uri: str, cache_dir: Path, client) -> Path:
    manifest = model_directory(solution) / "assets.sha256"
    target = cache_dir / "assets" / solution / file_digest(manifest)
    if target.exists():
        verify_assets(target, manifest)
        return target
    bucket, prefix = s3_location(uri)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=target.parent))
    try:
        for relative in manifest_files(manifest):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            key = "/".join(part for part in (prefix, relative) if part)
            client.download_file(bucket, key, str(destination))
        verify_assets(staging, manifest)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def archive_run(directory: Path, uri: str, client) -> str:
    bucket, prefix = s3_location(uri)
    paths = sorted(path for path in directory.rglob("*") if path.is_file())
    paths.sort(key=lambda path: path.name == "run.json")
    for path in paths:
        key = "/".join(part for part in (prefix, path.relative_to(directory).as_posix()) if part)
        client.upload_file(str(path), bucket, key)
    return uri.rstrip("/")


@contextmanager
def solution_lock(cache_dir: Path, solution: str):
    model_directory(solution)
    lock_dir = cache_dir / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / f"{solution}.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another {solution} run holds the persistent cache lock") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_command(command: list[str], cwd: Path, env: dict, log_path: Path, timeout: int, logger) -> None:
    if timeout <= 0:
        raise ValueError("Stage timeout must be positive")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    secrets = [value for key, value in env.items() if any(token in key.upper() for token in ("KEY", "SECRET", "TOKEN", "PASSWORD")) and value]

    def redact(text: str) -> str:
        for secret in sorted(secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        return text

    with log_path.open("w") as log:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )

        def capture():
            for line in process.stdout:
                safe_line = redact(line.rstrip())
                log.write(safe_line + "\n")
                log.flush()
                logger.info("%s", safe_line)

        reader = threading.Thread(target=capture, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=timeout)
            reader.join(timeout=5)
            if code:
                raise RuntimeError(f"Model stage {command[3]} exited with code {code}; see {log_path.name}")
        finally:
            if process.poll() is None or reader.is_alive():
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                reader.join(timeout=5)


def validate_forecast(path: Path, issue: date, sites: list[str], strict: bool = True):
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(path, dtype={"site_id": str, "issue_date": str, "model_version": str})
    required = {"site_id", "issue_date", "model_version", *(f"volume_{quantile}" for quantile in QUANTILES)}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Forecast is empty or missing required columns")
    if frame.site_id.duplicated().any() or set(frame.site_id) != set(sites):
        raise ValueError("Forecast must contain exactly one row per eligible requested site")
    if not frame.issue_date.eq(issue.isoformat()).all():
        raise ValueError("Forecast issue_date differs from requested issue date")
    if frame.model_version.isna().any() or frame.model_version.str.strip().eq("").any():
        raise ValueError("Forecast model_version is missing")
    if strict and frame.model_version.str.contains("_partial", regex=False).any():
        raise ValueError("Strict ensemble mode does not accept partial model versions")
    values = frame[[f"volume_{quantile}" for quantile in QUANTILES]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(values.to_numpy()).all() or (values < 0).any().any():
        raise ValueError("Forecast volumes must be finite and nonnegative")
    if not ((values.volume_10 <= values.volume_50) & (values.volume_50 <= values.volume_90)).all():
        raise ValueError("Forecast quantiles are not ordered")
    frame[values.columns] = values
    return frame