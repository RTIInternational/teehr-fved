"""Invoke the CRMMS RiverWare model via CLI or RCL script."""

import argparse
import re
import subprocess
import time
from pathlib import Path

_DEFAULT_RIVERWARE_EXE = Path(r"C:\FVED\Programs\RiverWare\RiverWare 9.7\RiverWare.exe")
_DEFAULT_MRM_RUN_NAME = "Run_CBRFC_Ensemble_Fcst_RFC"

# Patterns sourced from observed run.log output
_PAT_MRM_STARTED = re.compile(r"------ MRM RUN STARTED ------")
_PAT_TRACE_STARTED = re.compile(
    r"------ Rulebased Simulation RUN STARTED \(MRM run (\d+) of (\d+), trace (\d+)\) ------"
)
_PAT_MRM_FINISHED = re.compile(r"------ MRM RUN FINISHED ------")
_PAT_ERROR = re.compile(r"_ERROR_")


def find_mdl_file(model_dir: Path) -> Path:
    matches = list((model_dir / "RW Files").glob("*.mdl"))
    if not matches:
        raise FileNotFoundError(f"No .mdl file found in {model_dir / 'RW Files'}")
    if len(matches) > 1:
        raise ValueError(
            f"Multiple .mdl files found in {model_dir / 'RW Files'}: "
            + ", ".join(m.name for m in matches)
        )
    return matches[0]


def write_rcl(mdl_path: Path, mrm_run_name: str, rcl_path: Path) -> None:
    content = (
        "# Load the model\n"
        f"OpenWorkspace {{{mdl_path}}}\n"
        "# run the simulation\n"
        f"StartController !MRM {mrm_run_name}\n"
        "# Close the opened model and exit RiverWare\n"
        "CloseWorkspace\n"
    )
    rcl_path.write_text(content)
    print(f"RCL written: {rcl_path}")


def launch_riverware(
    riverware_exe: Path, rcl_path: Path, log_path: Path
) -> subprocess.Popen:
    cmd = [str(riverware_exe), "--batch", str(rcl_path), "--log", str(log_path)]
    print(f"Launching: {' '.join(cmd)}")
    return subprocess.Popen(cmd)


def monitor_log(log_path: Path, proc: subprocess.Popen, poll_interval: float = 2.0) -> None:
    # Wait for RiverWare to create the log file
    print(f"Waiting for log file: {log_path}")
    while not log_path.exists():
        if proc.poll() is not None:
            raise RuntimeError(
                f"RiverWare exited (code {proc.returncode}) before log file was created."
            )
        time.sleep(poll_interval)

    finished = False
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        while True:
            line = fh.readline()
            if not line:
                if proc.poll() is not None and not finished:
                    raise RuntimeError(
                        f"RiverWare exited (code {proc.returncode}) before MRM RUN FINISHED."
                    )
                time.sleep(poll_interval)
                continue

            line = line.rstrip()

            if _PAT_MRM_STARTED.search(line):
                print("MRM run started.")

            elif m := _PAT_TRACE_STARTED.search(line):
                run_n, total, trace = m.group(1), m.group(2), m.group(3)
                print(f"  Trace {trace} — MRM run {run_n}/{total} started.")

            elif _PAT_MRM_FINISHED.search(line):
                print("MRM run finished successfully.")
                finished = True
                break

            elif _PAT_ERROR.search(line):
                print(f"  [ERROR] {line}")

    if not finished:
        raise RuntimeError("Log monitoring ended without detecting MRM RUN FINISHED.")


def run_crmms(
    model_dir: Path,
    mdl_filename: str | None = None,
    mrm_run_name: str = _DEFAULT_MRM_RUN_NAME,
    riverware_exe: Path = _DEFAULT_RIVERWARE_EXE,
) -> None:
    model_dir = model_dir.resolve()

    mdl_path = (
        model_dir / "RW Files" / mdl_filename
        if mdl_filename
        else find_mdl_file(model_dir)
    )
    if not mdl_path.exists():
        raise FileNotFoundError(f"Model file not found: {mdl_path}")

    rcl_path = model_dir / "run_esp_mrm.rcl"
    log_path = model_dir / "run.log"

    write_rcl(mdl_path, mrm_run_name, rcl_path)
    proc = launch_riverware(riverware_exe, rcl_path, log_path)
    monitor_log(log_path, proc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the CRMMS RiverWare model in batch mode."
    )
    parser.add_argument(
        "--model-dir",
        required=True,
        type=Path,
        help="Path to the CRMMS model folder (e.g. C:\\FVED\\Models\\CRMMS-ESP\\CRMMS-March2025)",
    )
    parser.add_argument(
        "--mdl-filename",
        default=None,
        help="Name of the .mdl file inside 'RW Files\\'. Auto-discovered if omitted.",
    )
    parser.add_argument(
        "--mrm-run-name",
        default=_DEFAULT_MRM_RUN_NAME,
        help=f"MRM run controller name (default: {_DEFAULT_MRM_RUN_NAME})",
    )
    parser.add_argument(
        "--riverware-exe",
        default=_DEFAULT_RIVERWARE_EXE,
        type=Path,
        help=f"Path to RiverWare.exe (default: {_DEFAULT_RIVERWARE_EXE})",
    )
    args = parser.parse_args()

    run_crmms(
        model_dir=args.model_dir,
        mdl_filename=args.mdl_filename,
        mrm_run_name=args.mrm_run_name,
        riverware_exe=args.riverware_exe,
    )

