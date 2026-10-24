"""Shared helpers for RiverWare file I/O, date handling, and common utilities."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

# Matches: Begin date "24:00 Mar 31 2025"
_LOG_BEGIN_DATE_RE = re.compile(r'Begin date "24:00 (\w{3} \d{1,2} \d{4})"')


def _parse_rdf_timestamp(ts_str: str) -> datetime:
    """Convert a RiverWare end-of-period '24:00' timestamp to a UTC datetime."""
    date_part, time_part = ts_str.strip().split(" ", 1)
    y, m, d = date_part.split("-")
    dt = datetime(int(y), int(m), int(d), tzinfo=timezone.utc)
    if time_part.strip() == "24:00":
        dt += timedelta(days=1)
    return dt


def parse_rdf(rdf_path: Path) -> Iterator[dict]:
    """Yield one record dict per (trace, timestep, slot) from an RDF file."""
    with open(rdf_path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [line.rstrip("\n\r") for line in fh]

    pos = 0
    n = len(lines)

    def read_kv_block(sentinel: str) -> dict:
        nonlocal pos
        data: dict = {}
        while pos < n:
            line = lines[pos]
            pos += 1
            if line.strip() == sentinel:
                break
            if ":" in line:
                key, _, val = line.partition(":")
                data[key.strip()] = val.strip()
        return data

    # Package preamble
    meta = read_kv_block("END_PACKAGE_PREAMBLE")
    n_runs = int(meta.get("number_of_runs", 0))

    for _ in range(n_runs):
        run = read_kv_block("END_RUN_PREAMBLE")
        trace = run.get("trace", "")
        # RiverWare uses 'time_steps' or 'timesteps' depending on version
        n_ts = int(run.get("time_steps", run.get("timesteps", 0)))

        timestamps = [lines[pos + i] for i in range(n_ts)]
        pos += n_ts

        while pos < n:
            slot = read_kv_block("END_SLOT_PREAMBLE")
            if not slot:
                break

            object_name = slot.get("object_name", "")
            slot_name = slot.get("slot_name", "")

            _, _, unit_raw = lines[pos].partition(":"); pos += 1
            unit_name = unit_raw.strip()
            if unit_name.upper() == "NONE":
                unit_name = ""

            _, _, scale_raw = lines[pos].partition(":"); pos += 1
            scale = float(scale_raw.strip())

            values: list[float] = []
            while pos < n and lines[pos].strip() != "END_COLUMN":
                raw = lines[pos].strip()
                pos += 1
                values.append(
                    float("nan") if raw.upper() == "NAN" else float(raw) * scale
                )

            # lines[pos]=END_COLUMN, lines[pos+1]=END_SLOT, lines[pos+2]=END_RUN or next slot
            is_last = (pos + 2 < n) and lines[pos + 2].strip() == "END_RUN"
            pos += 2  # skip END_COLUMN and END_SLOT
            if is_last:
                pos += 1  # skip END_RUN

            # Only yield rows for series slots (scalar slots have 1 value)
            if len(values) == n_ts:
                for ts_raw, val in zip(timestamps, values):
                    yield {
                        "trace": trace,
                        "value_time": _parse_rdf_timestamp(ts_raw),
                        "object_name": object_name,
                        "slot_name": slot_name,
                        "unit_name": unit_name,
                        "value": val,
                    }

            if is_last:
                break


def parse_reference_time_from_log(log_path: Path) -> datetime:
    """Extract model init date from the first 'Begin date' entry in run.log."""
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_BEGIN_DATE_RE.search(line)
            if m:
                # 24:00 end-of-period → add one day for UTC midnight equivalent
                dt = datetime.strptime(m.group(1), "%b %d %Y").replace(tzinfo=timezone.utc)
                return dt + timedelta(days=1)
    raise ValueError(f"No 'Begin date' entry found in log: {log_path}")
