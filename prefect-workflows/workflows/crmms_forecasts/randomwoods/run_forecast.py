"""
RandomWoods forecast — Python execution wrapper.

This module provides a plain, framework-agnostic function that invokes the
refactored RandomWoods R script (r/RandomWoods_Forecast.R) via subprocess.
`download_inputs.py`, colocated in this same folder, downloads the annual
Lees Ferry naturalized flow + AMO/PDO inputs this script needs before a run.

Scope note: this is intentionally NOT a Prefect flow yet. It is the
callable "core" a @task/@flow can wrap directly, following the same
pattern as workflows/riverware/ elsewhere in this repo -- e.g.:

    from prefect import flow, task
    from workflows.crmms_forecasts.randomwoods.run_forecast import run_r_forecast

    @task
    def run_r_forecast_task(work_dir, end_year):
        run_r_forecast(work_dir, end_year)

For now, use this module directly (see __main__ below) or import
`run_r_forecast` to test the R execution path locally / in Docker.
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("randomwoods.run_forecast")

# Directory containing RandomWoods_Forecast.R and the sourced R library,
# relative to this file -- independent of the caller's working directory.
R_SCRIPT_DIR = Path(__file__).resolve().parent / "r"
R_SCRIPT_NAME = "RandomWoods_Forecast.R"


def default_end_year(today: datetime | None = None) -> int:
    """Water year to forecast, derived the same way the R script derives it.

    Water year starts Oct 1: if the current month is >= October, the
    forecast targets the *next* calendar year; otherwise the current year.
    """
    today = today or datetime.now(timezone.utc)
    return today.year + 1 if today.month >= 10 else today.year


def run_r_forecast(
    work_dir: str | Path,
    end_year: int | None = None,
    *,
    output_dir: str | Path | None = None,
    lf_natflow_file: str | None = None,
    amo_file: str | None = None,
    pdo_file: str | None = None,
    static_data_dir: str | Path | None = None,
    random_seed: int | None = 42,
    generate_plots: bool | None = None,
    r_script_dir: str | Path = R_SCRIPT_DIR,
    timeout_seconds: int = 30 * 60,
) -> subprocess.CompletedProcess:
    """Run the RandomWoods R forecast script as a subprocess.

    Parameters
    ----------
    work_dir : str or Path
        Directory containing the *annually updated* naturalized flow
        workbook and AMO/PDO index files. Also the default location for
        outputs. See download_inputs.py (colocated in this same folder)
        for the script that populates this directory once a year.
    end_year : int, optional
        Water year to forecast. Auto-derived from the system date if omitted.
    output_dir : str or Path, optional
        Where forecast outputs (CSV/PNG/PDF) are written. Defaults to work_dir.
    lf_natflow_file : str, optional
        Filename of the naturalized flow workbook within work_dir. Defaults
        to the R script's own default (see RandomWoods_Forecast.R).
    amo_file : str, optional
        Filename of the AMO ocean index file within work_dir. Defaults to
        "AMO_latest.dat" (see download_inputs.py).
    pdo_file : str, optional
        Filename of the PDO ocean index file within work_dir. Defaults to
        "PDO_latest.dat" (see download_inputs.py).
    static_data_dir : str or Path, optional
        Directory containing the three CESM-LE quantile txt files (these
        never change until after WY2080).
        Defaults to the R script's own default, ./static_data relative to
        this folder, or wherever it's baked into the Docker image.
    random_seed : int, optional
        RNG seed passed to the R script for reproducible randomForest
        training/bootstrapping. Defaults to 42; pass None to let the R
        script use its own default instead.
    generate_plots : bool, optional
        Whether to generate PNG/PDF plots in addition to the forecast CSV.
        Defaults to None, which leaves it to the R script's own default
        (True) or the container's GENERATE_PLOTS env var. Pass False for a
        lean, CSV-only operational run -- this also lets a Docker image
        built with INSTALL_PLOT_PACKAGES=false (no ggplot2/gghalves/
        patchwork) run successfully.
    r_script_dir : str or Path
        Directory holding RandomWoods_Forecast.R and the R library file.
    timeout_seconds : int
        Hard ceiling on subprocess runtime.

    Returns
    -------
    subprocess.CompletedProcess
        Raises RuntimeError if the R script exits non-zero.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if end_year is None:
        end_year = default_end_year()

    r_script = Path(r_script_dir) / R_SCRIPT_NAME
    if not r_script.exists():
        raise FileNotFoundError(f"R script not found: {r_script}")

    env = os.environ.copy()
    env["FORECAST_YEAR"] = str(end_year)
    env["WORK_DIR"] = str(work_dir)
    if generate_plots is not None:
        env["GENERATE_PLOTS"] = "true" if generate_plots else "false"
    if static_data_dir is not None:
        env["STATIC_DATA_DIR"] = str(static_data_dir)
    if output_dir is not None:
        env["OUTPUT_DIR"] = str(output_dir)
    if lf_natflow_file is not None:
        env["LF_NATFLOW_FILE"] = lf_natflow_file
    if amo_file is not None:
        env["AMO_FILE"] = amo_file
    if pdo_file is not None:
        env["PDO_FILE"] = pdo_file
    if random_seed is not None:
        env["RANDOM_SEED"] = str(random_seed)

    logger.info("Running RandomWoods R forecast for WY%s in %s", end_year, work_dir)

    result = subprocess.run(
        ["Rscript", str(r_script)],
        cwd=str(work_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    for line in result.stdout.splitlines():
        logger.info("[R] %s", line)
    for line in result.stderr.splitlines():
        logger.warning("[R stderr] %s", line)

    if result.returncode != 0:
        raise RuntimeError(
            f"RandomWoods R script failed with return code {result.returncode}"
        )

    logger.info("RandomWoods WY%s forecast completed successfully", end_year)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the RandomWoods R forecast locally.")
    parser.add_argument("--work-dir", required=True, help="Directory with input files / outputs")
    parser.add_argument("--end-year", type=int, default=None, help="Water year to forecast")
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="RNG seed for reproducible randomForest training (default: 42)",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip PNG/PDF plot generation; write only the forecast CSV",
    )
    args = parser.parse_args()

    run_r_forecast(
        args.work_dir,
        args.end_year,
        random_seed=args.random_seed,
        generate_plots=not args.no_plots,
    )
