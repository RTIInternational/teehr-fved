"""Download the inputs of the 1st place live model for a given issue date.

Into <root>/data (competition-runtime layout, read by the unmodified live feature code):
  * USGS streamflow, SNOTEL and CDEC snow: the competition's own `wsfr_download bulk` (pinned in environment.yml, the same
    sources as the live stage) into <root>/downloads/wsfr; the current-year FY directories are linked into data/.
    The CDEC / SNOTEL station mappings are the *training* mappings from static/ (feature_parameters were built with them),
    not the ones the downloader regenerates. The end date is the issue date (exclusive); the current year is always re-fetched.
  * monthly naturalized flow ("variant A"): see monthly_flow.py.
  * submission_format.csv: the single issue date the live code is asked to predict.

Not downloaded here because the core code fetches them itself during `predict` (with patches 002/003): UA SWANN gridded snow
(snowview.arizona.edu), ACIS station precipitation/temperature, and the alternative USGS NWIS gauges (the 8 reservoir/inflow
sites whose competition gauge is not a natural-flow gauge).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from . import monthly_flow
from .paths import PKG_DIR, Paths

STATIC = PKG_DIR / "static"
SOURCES = ["usgs_streamflow", "snotel", "cdec"]
FY_SOURCES = ["usgs_streamflow", "snotel", "cdec"]


def check_issue_date(issue_date: date) -> None:
    if not 1 <= issue_date.month <= 7:
        raise ValueError(f"the 1st place model only forecasts for issue dates in January-July (got {issue_date})")


def setup_data_dir(paths: Paths, issue_date: date) -> None:
    data = paths.data
    for sub in ("snotel", "cdec"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    for name in ("metadata.csv", "geospatial.gpkg", "cdec_snow_stations.csv"):
        shutil.copy2(STATIC / name, data / name)
    shutil.copy2(STATIC / "snotel" / "sites_to_snotel_stations.csv", data / "snotel" / "sites_to_snotel_stations.csv")
    shutil.copy2(STATIC / "cdec" / "sites_to_cdec_stations.csv", data / "cdec" / "sites_to_cdec_stations.csv")
    meta = pd.read_csv(data / "metadata.csv")
    grid = pd.DataFrame({"site_id": meta.site_id, "issue_date": issue_date.isoformat(), "volume_10": 0.0, "volume_50": 0.0, "volume_90": 0.0})
    grid.to_csv(data / "submission_format.csv", index=False)


def run_wsfr_bulk(paths: Paths, issue_date: date, refresh: bool = True) -> Path:
    dl_root = paths.downloads / "wsfr"
    dl_root.mkdir(parents=True, exist_ok=True)
    for name in ("metadata.csv", "geospatial.gpkg", "cdec_snow_stations.csv"):
        shutil.copy2(paths.data / name, dl_root / name)
    cfg = dl_root / f"bulk_FY{issue_date.year}.yml"
    cfg.write_text(
        f"forecast_years: [{issue_date.year}]\nfy_start_month: 10\nfy_start_day: 1\n"
        f"fy_end_month: {issue_date.month}\nfy_end_day: {issue_date.day}\n"
        f"skip_existing: {str(not refresh).lower()}\n"
        "data_sources:\n" + "".join(f"  - name: {s}\n" for s in SOURCES)
    )
    subprocess.run([sys.executable, "-m", "wsfr_download", "bulk", str(cfg)], check=True, env={**os.environ, "WSFR_DATA_ROOT": str(dl_root)})
    return dl_root


def link_forecast_year(paths: Paths, dl_root: Path, year: int) -> None:
    for sub in FY_SOURCES:
        src, dst = dl_root / sub / f"FY{year}", paths.data / sub / f"FY{year}"
        if not src.is_dir():
            raise RuntimeError(f"download produced no {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink() if dst.is_symlink() else shutil.rmtree(dst)
        dst.symlink_to(src)


def coverage_report(paths: Paths, year: int) -> list[str]:
    """Warnings for stations / gauges with no usable data (the live code silently averages over what is present)."""
    warnings = []
    snotel_map = pd.read_csv(paths.data / "snotel" / "sites_to_snotel_stations.csv")
    empty = []
    for st in sorted(set(snotel_map.stationTriplet)):
        f = paths.data / "snotel" / f"FY{year}" / f"{st.replace(':', '_')}.csv"
        if not f.exists() or pd.read_csv(f).filter(["PREC_DAILY", "WTEQ_DAILY"]).dropna(how="all").empty:
            empty.append(st)
    if empty:
        warnings.append(f"SNOTEL FY{year}: {len(empty)} of {snotel_map.stationTriplet.nunique()} mapped stations have no data (e.g. {empty[:3]})")

    cdec_map = pd.read_csv(paths.data / "cdec" / "sites_to_cdec_stations.csv")
    cdec_dir = paths.data / "cdec" / f"FY{year}"
    have = {p.stem for p in cdec_dir.glob("*.csv")}
    missing = sorted(set(cdec_map.station_id) - have)
    if missing:
        warnings.append(f"CDEC FY{year}: {len(missing)} of {cdec_map.station_id.nunique()} mapped stations have no file")

    meta = pd.read_csv(paths.data / "metadata.csv")
    alt = {"ruedi_reservoir_inflow", "fontenelle_reservoir_inflow", "american_river_folsom_lake", "skagit_ross_reservoir",
           "boysen_reservoir_inflow", "pueblo_reservoir_inflow", "boise_r_nr_boise", "sweetwater_r_nr_alcova"}
    usgs = {p.stem for p in (paths.data / "usgs_streamflow" / f"FY{year}").glob("*.csv")}
    no_usgs = sorted(set(meta[meta.usgs_id.notna()].site_id) - usgs - alt)
    if no_usgs:
        warnings.append(f"USGS FY{year}: no file for {no_usgs}")
    return warnings


def leakage_report(paths: Paths, issue_date: date) -> list[str]:
    """Any input row dated on/after the issue date (must be empty: the model may only see data before it)."""
    cutoff = pd.Timestamp(issue_date)
    bad = []
    for sub, col in (("snotel", "date"), ("usgs_streamflow", "datetime"), ("cdec", None)):
        for f in (paths.data / sub / f"FY{issue_date.year}").glob("*.csv"):
            if f.name.startswith("station_metadata"):
                continue
            df = pd.read_csv(f)
            c = col or next((c for c in df.columns if "date" in c.lower()), None)
            if c is None:
                continue
            d = pd.to_datetime(df[c], utc=True).dt.tz_localize(None)
            if (d >= cutoff).any():
                bad.append(f"{sub}/{f.name}: rows on/after {issue_date}")
    mf = paths.data / "test_monthly_naturalized_flow.csv"
    if mf.exists():
        m = pd.read_csv(mf)
        if not all(monthly_flow._month_ended(int(y), int(mo), issue_date) for y, mo in zip(m.year, m.month)):
            bad.append("test_monthly_naturalized_flow.csv: months not complete before the issue date")
    return bad


def download(paths: Paths, issue_date: date, refresh: bool = True) -> None:
    check_issue_date(issue_date)
    paths.ensure()
    setup_data_dir(paths, issue_date)
    dl_root = run_wsfr_bulk(paths, issue_date, refresh)
    link_forecast_year(paths, dl_root, issue_date.year)
    monthly_flow.download(paths.data / "metadata.csv", issue_date, paths.data / "test_monthly_naturalized_flow.csv")
    leaks = leakage_report(paths, issue_date)
    if leaks:
        raise RuntimeError("data leakage past the issue date:\n  " + "\n  ".join(leaks))
    for w in coverage_report(paths, issue_date.year):
        print("WARNING", w, file=sys.stderr)
