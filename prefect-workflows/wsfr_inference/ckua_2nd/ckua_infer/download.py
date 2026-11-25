"""Download the inputs of the 2nd place live model for a given issue date.

SNOTEL and USGS daily streamflow come from the competition's own `wsfr_download bulk` (pinned in environment.yml), the same
code and data sources the live stage used, into <root>/downloads/wsfr; the FY directory of the forecast year is linked into
<root>/data. The SNOTEL station mapping is the *training* mapping shipped in static/ (the model's per-site station sets in
snotel_lrs.pkl were built with it), not the one the downloader regenerates. The download end date is the issue date
(exclusive), so no data on or after it is ever fetched. The current forecast year is always re-downloaded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from . import monthly_flow
from .paths import PKG_DIR, Paths

STATIC = PKG_DIR / "static"
BULK_ATTEMPTS = 4
BULK_BACKOFF_S = 30


def setup_data_dir(paths: Paths) -> None:
    paths.data.mkdir(parents=True, exist_ok=True)
    (paths.data / "snotel").mkdir(exist_ok=True)
    shutil.copy2(STATIC / "metadata.csv", paths.data / "metadata.csv")
    shutil.copy2(STATIC / "geospatial.gpkg", paths.data / "geospatial.gpkg")
    shutil.copy2(STATIC / "snotel" / "sites_to_snotel_stations.csv", paths.data / "snotel" / "sites_to_snotel_stations.csv")


def run_wsfr_bulk(paths: Paths, issue_date: date, refresh: bool = True) -> Path:
    fy = monthly_flow.forecast_year(issue_date)
    dl_root = paths.downloads / "wsfr"
    dl_root.mkdir(parents=True, exist_ok=True)
    for name in ("metadata.csv", "geospatial.gpkg"):
        shutil.copy2(paths.data / name, dl_root / name)
    cfg = dl_root / f"bulk_FY{fy}.yml"
    cfg.write_text(
        f"forecast_years: [{fy}]\nfy_start_month: 10\nfy_start_day: 1\n"
        f"fy_end_month: {issue_date.month}\nfy_end_day: {issue_date.day}\n"
        f"skip_existing: {str(not refresh).lower()}\n"
        "data_sources:\n  - name: usgs_streamflow\n  - name: snotel\n"
    )
    cmd = [sys.executable, "-m", "wsfr_download", "bulk", str(cfg)]
    env = {**os.environ, "WSFR_DATA_ROOT": str(dl_root)}
    # USGS/NRCS endpoints return transient 5xx; the pinned downloader doesn't retry. Always re-run the whole bulk (never switch to
    # skip_existing on retry, which would keep stale files from an earlier issue date).
    for attempt in range(1, BULK_ATTEMPTS + 1):
        try:
            subprocess.run(cmd, check=True, env=env)
            break
        except subprocess.CalledProcessError:
            if attempt == BULK_ATTEMPTS:
                raise
            wait = BULK_BACKOFF_S * attempt
            print(f"wsfr_download failed (attempt {attempt}/{BULK_ATTEMPTS}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    return dl_root


def link_forecast_year(paths: Paths, dl_root: Path, fy: int) -> None:
    for sub in ("snotel", "usgs_streamflow"):
        src, dst = dl_root / sub / f"FY{fy}", paths.data / sub / f"FY{fy}"
        if not src.is_dir():
            raise RuntimeError(f"download produced no {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink() if dst.is_symlink() else shutil.rmtree(dst)
        dst.symlink_to(src)


def coverage_report(paths: Paths, fy: int) -> list[str]:
    """Warnings for SNOTEL stations / USGS sites with no usable data (a missing station silently drops the SNOTEL feature)."""
    import pandas as pd

    warnings = []
    mapping = pd.read_csv(paths.data / "snotel" / "sites_to_snotel_stations.csv")
    snotel_dir = paths.data / "snotel" / f"FY{fy}"
    empty = []
    for st in sorted(set(mapping.stationTriplet)):
        f = snotel_dir / f"{st.replace(':', '_')}.csv"
        # station files have only the sensors that station reports
        if not f.exists() or pd.read_csv(f).filter(["PREC_DAILY", "WTEQ_DAILY"]).dropna(how="all").empty:
            empty.append(st)
    if empty:
        warnings.append(f"SNOTEL FY{fy}: {len(empty)} of {mapping.stationTriplet.nunique()} mapped stations have no data (e.g. {empty[:3]})")
    meta = pd.read_csv(paths.data / "metadata.csv")
    usgs = {p.stem for p in (paths.data / "usgs_streamflow" / f"FY{fy}").glob("*.csv")}
    no_usgs = sorted(set(meta[meta.usgs_id.notna()].site_id) - usgs)
    if no_usgs:
        warnings.append(f"USGS FY{fy}: no file for {no_usgs}")
    return warnings


def leakage_report(paths: Paths, issue_date: date) -> list[str]:
    """Any input row dated on/after the issue date (must be empty: the model may only see data before it)."""
    import pandas as pd

    fy = monthly_flow.forecast_year(issue_date)
    cutoff = pd.Timestamp(issue_date)
    bad = []
    for sub, col in (("snotel", "date"), ("usgs_streamflow", "datetime")):
        for f in (paths.data / sub / f"FY{fy}").glob("*.csv"):
            if f.name.startswith("station_metadata"):
                continue
            d = pd.to_datetime(pd.read_csv(f, usecols=[col])[col], utc=True).dt.tz_localize(None)
            if (d >= cutoff).any():
                bad.append(f"{sub}/{f.name}: rows on/after {issue_date}")
    mf = paths.data / "test_monthly_naturalized_flow.csv"
    if mf.exists():
        m = pd.read_csv(mf)
        ended = [monthly_flow._month_ended(int(y), int(mo), issue_date) for y, mo in zip(m.year, m.month)]
        if not all(ended):
            bad.append("test_monthly_naturalized_flow.csv: months not complete before the issue date")
    return bad


def download(paths: Paths, issue_date: date, refresh: bool = True) -> None:
    fy = monthly_flow.forecast_year(issue_date)
    paths.ensure()
    setup_data_dir(paths)
    dl_root = run_wsfr_bulk(paths, issue_date, refresh)
    link_forecast_year(paths, dl_root, fy)
    monthly_flow.download(paths.data / "metadata.csv", issue_date, paths.data / "test_monthly_naturalized_flow.csv")
    leaks = leakage_report(paths, issue_date)
    if leaks:
        raise RuntimeError("data leakage past the issue date:\n  " + "\n  ".join(leaks))
    for w in coverage_report(paths, fy):
        print("WARNING", w, file=sys.stderr)
