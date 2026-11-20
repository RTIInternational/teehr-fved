"""Download the inputs of the 3rd place model for a given issue date into <root>/downloads (and the monthly flow into <root>/data).

Only the forecast water year is needed (Oct 1 of the previous year up to the issue date); every source is re-fetched on each run
(the newest days of most sources are revised) except the immutable ones noted below.

  snotel, cdec, usgs_streamflow, pdsi   the competition's `wsfr_download` functions with the same call parameters as the 3rd place
                                        scripts (own SNOTEL station list, PDSI from Dec 1); end date = issue date (inclusive; its value is never a feature, but the row must exist)
  usbr                                  vendored `src.data.usbr.download_usbr` (RISE), Jan 1 .. issue date - 1; one file per site
  uaswann/raw/daily                     UA SWANN 4 km daily NetCDF. The file suffix depends on the age of the day (_early, _provisional,
                                        _stable); newer tiers replace older files. (The vendored downloader only knows `_stable`.)
  uaswann/raw/huc{6,8}                  UA SnowView watershed time series, converted to the column names the vendored reader expects
                                        (the endpoint moved to snowview.arizona.edu and renamed its columns; values are identical)
  era5                                  ERA5-Land for the day before the issue date only (the only day the features read), via CDS
  seas51                                SEAS5.1 initialisations Dec (year-1) .. issue month, via CDS (a month is published ~5th)
  data/test_monthly_naturalized_flow.csv   monthly naturalized flow (variant A), see monthly_flow.py

Latency decides which variants can run on a given day: see solution.source_report.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import engine, monthly_flow
from .paths import PKG_DIR, Paths

STATIC = PKG_DIR / "static"
SWANN_TIERS = ["stable", "provisional", "early"]  # best first
SWANN_URL = "https://climate.arizona.edu/data/UA_SWE/DailyData_4km/WY{wy}/UA_SWE_Depth_4km_v1_{day}_{tier}.nc"
SNOWVIEW_URL = "https://snowview.arizona.edu/csv/Download/Watersheds/{huc}.csv"
HUC_RENAME = {"overall_mean_swe_in": "Average SWE (in)", "overall_cumulative_precip_in": "Average Accumulated Water Year PPT (in)"}


def check_issue_date(issue_date: date) -> None:
    if not 1 <= issue_date.month <= 7:
        raise ValueError(f"the 3rd place model only forecasts for issue dates in January-July (got {issue_date})")


def setup_data_dir(paths: Paths) -> None:
    for name in ("metadata.csv", "geospatial.gpkg", "cdec_snow_stations.csv"):
        shutil.copy2(STATIC / "raw" / name, paths.data / name)


def _fy_start(issue_date: date) -> date:
    return date(issue_date.year - 1, 10, 1)


# --- wsfr_download sources ----------------------------------------------------------------------------------------
def _wsfr(name: str):
    """Import a wsfr_download module. Its config does `logger.remove(0)` at import, which raises when the vendored code (or any
    earlier import) already removed loguru's default handler; tolerate that."""
    from loguru import logger

    original = logger.remove

    def tolerant(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except ValueError:
            return None

    logger.remove = tolerant
    try:
        return importlib.import_module(f"wsfr_download.{name}")
    finally:
        logger.remove = original


def snotel(paths: Paths, issue_date: date, workers: int = 8) -> list[str]:
    download_station_data = _wsfr("snotel").download_station_data

    df = pd.read_feather(STATIC / "meta" / "snotel_sites_basins" / "snotel_sites_flag.feather")
    df["is_elig"] = df.filter(like="is_").sum(axis=1) > 0
    triplets = df.query("is_elig")["snotel_triplet"].tolist()
    out = paths.downloads / "snotel" / f"FY{issue_date.year}"
    out.mkdir(parents=True, exist_ok=True)
    begin, end = pd.Timestamp(_fy_start(issue_date)), pd.Timestamp(issue_date)

    def one(t):
        for _ in range(3):
            try:
                download_station_data(t, begin_date=begin, end_date=end, out_dir=out, skip_existing=False)
                return None
            except Exception as e:  # noqa: BLE001
                err = repr(e)
        return f"{t}: {err}"

    with ThreadPoolExecutor(workers) as pool:
        failed = [r for r in pool.map(one, triplets) if r]
    return [f"SNOTEL: {len(failed)} of {len(triplets)} stations failed (e.g. {failed[:2]})"] if failed else []


def cdec(paths: Paths, issue_date: date) -> list[str]:
    m = _wsfr("cdec")

    m.CDEC_DIR = paths.downloads / "cdec"
    end = issue_date + timedelta(days=1)  # the wsfr end day is exclusive; the issue day's own row is needed (its value is never a feature)
    m.download_cdec(
        forecast_years=[issue_date.year], fy_start_month=10, fy_start_day=1,
        fy_end_month=end.month, fy_end_day=end.day, skip_existing=False,
    )
    return []


def usgs(paths: Paths, issue_date: date) -> list[str]:
    m = _wsfr("usgs_streamflow")

    m.DATA_ROOT = paths.downloads
    end = issue_date + timedelta(days=1)
    m.download_usgs_streamflow(
        forecast_years=[issue_date.year], fy_start_month=10, fy_start_day=1,
        fy_end_month=end.month, fy_end_day=end.day, skip_existing=False,
    )
    return []


def pdsi(paths: Paths, issue_date: date) -> list[str]:
    m = _wsfr("pdsi")

    fy_dir = paths.downloads / "pdsi" / "pdsi" / f"FY{issue_date.year}"
    if fy_dir.exists():  # the file name carries the end date: a stale file would duplicate dates with different values
        shutil.rmtree(fy_dir)
    m.DATA_ROOT = paths.downloads / "pdsi"
    m.download_pdsi(
        forecast_years=[issue_date.year], fy_start_month=12, fy_start_day=1,
        fy_end_month=issue_date.month, fy_end_day=issue_date.day, skip_existing=False,
    )
    return []


def usbr(paths: Paths, issue_date: date) -> list[str]:
    from src.data.usbr import download_usbr, sites_items_mapping

    out = paths.downloads / "usbr"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.csv"):  # the reader sums duplicate dates: never keep two files for a site and year
        old.unlink()
    warnings = []
    for item_id, site in sites_items_mapping.items():
        download_usbr(f"{issue_date.year}-01-01", (issue_date - timedelta(days=1)).isoformat(), item_id, out)
        f = next(out.glob(f"*__{site}.csv"))
        if "Lake/Reservoir Inflow" not in f.read_text():
            warnings.append(f"USBR RISE: {site} returned no inflow data")
    return warnings


# --- UA SWANN -------------------------------------------------------------------------------------------------------
def _water_year(d: date) -> int:
    return d.year if d.month < 10 else d.year + 1


def swann_daily(paths: Paths, issue_date: date, workers: int = 8) -> list[str]:
    """One NetCDF per day Oct 1 .. issue date - 1. The tier of each file is remembered; only better tiers are re-requested."""
    out = paths.downloads / "uaswann" / "raw" / "daily"
    out.mkdir(parents=True, exist_ok=True)
    tiers_f = out.parent / "daily_tiers.json"
    tiers = json.loads(tiers_f.read_text()) if tiers_f.exists() else {}
    days = pd.date_range(_fy_start(issue_date), issue_date - timedelta(days=1)).date

    def one(d):
        key, f = d.strftime("%Y%m%d"), out / f"{d.strftime('%Y%m%d')}.nc"
        have = SWANN_TIERS.index(tiers[key]) if f.exists() and key in tiers else len(SWANN_TIERS)
        for i, tier in enumerate(SWANN_TIERS[:have]):
            try:
                r = requests.get(SWANN_URL.format(wy=_water_year(d), day=key, tier=tier), timeout=120)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.content[:3] in (b"CDF", b"\x89HD"):
                f.write_bytes(r.content)
                return key, tier
        return key, None

    with ThreadPoolExecutor(workers) as pool:
        for key, tier in pool.map(one, days):
            if tier:
                tiers[key] = tier
    tiers_f.write_text(json.dumps(tiers))
    missing = [d.isoformat() for d in days if not (out / f"{d.strftime('%Y%m%d')}.nc").exists()]
    return [f"UA SWANN daily: {len(missing)} of {len(days)} days unavailable (latest {days[-1]}; missing e.g. {missing[-3:]})"] if missing else []


def swann_huc(paths: Paths, issue_date: date) -> list[str]:
    """HUC6/HUC8 watershed series for every watershed the model uses (legacy column names, legacy file layout)."""
    sites = pd.read_feather(STATIC / "meta" / "nwis_usgs_meta.feather")
    meta = pd.read_csv(STATIC / "raw" / "metadata.csv", dtype={"usgs_id": "object"})
    sites["huc"] = sites["huc_cd"].astype(str).str.zfill(8)
    sites = sites[sites["usgs_id"].isin(meta.usgs_id.dropna().tolist() + ["12175500"])]  # 12175500: Skagit proxy, as in the core
    warnings = []
    for level, hucs in ((6, sites.huc.str[:6].unique()), (8, sites.huc.str[:8].unique())):
        out = paths.downloads / "uaswann" / "raw" / f"huc{level}"
        out.mkdir(parents=True, exist_ok=True)
        for huc in hucs:
            try:
                r = requests.get(SNOWVIEW_URL.format(huc=huc), timeout=120)
                r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text), comment="#")
                df = df.rename(columns={"date": "Date", **HUC_RENAME})[["Date", *HUC_RENAME.values()]]
                if df.empty:
                    raise ValueError("empty")
                df.to_csv(out / f"{huc}.csv", index=False)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"UA SnowView HUC{level} {huc}: {type(e).__name__}: {e}" + (" (kept previous file)" if (out / f'{huc}.csv').exists() else ""))
    return warnings


# --- Copernicus CDS -----------------------------------------------------------------------------------------------
def _cds_client():
    import cdsapi

    return cdsapi.Client()


def era5_day(paths: Paths, issue_date: date) -> list[str]:
    """ERA5-Land at 00:00/23:00 UTC of issue_date - 1 (what the issue date's features read); same request as src.data.cds.download_era5."""
    from src.data.cds import _conus_bbox, _era5_cols

    d = issue_date - timedelta(days=1)
    raw = paths.downloads / "era5" / "raw"
    target = raw / f"{d.isoformat()}_era5land"
    if any(target.glob("*.nc")):
        return []
    raw.mkdir(parents=True, exist_ok=True)
    zip_path = raw / f"{d.isoformat()}_era5land.zip"
    try:
        _cds_client().retrieve(
            "reanalysis-era5-land",
            {
                "variable": _era5_cols, "time": ["00:00", "23:00"], "year": str(d.year), "month": f"{d.month:02d}",
                "day": [f"{d.day:02d}"], "area": _conus_bbox, "data_format": "netcdf_legacy", "download_format": "zip",
            },
            str(zip_path),
        )
    except Exception as e:  # noqa: BLE001
        zip_path.unlink(missing_ok=True)
        return [f"ERA5-Land {d}: not available yet ({type(e).__name__}: {str(e)[:120]}); era5 variants will be left out"]
    target.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target)
    zip_path.unlink()
    return []


def seas51(paths: Paths, issue_date: date) -> list[str]:
    """SEAS5.1 monthly initialisations Dec (year-1) .. issue month, lead month 1. Existing files are kept."""
    from src.data.cds import download_seas51_monthly

    warnings = []
    months = [(issue_date.year - 1, 12)] + [(issue_date.year, m) for m in range(1, issue_date.month + 1)]
    for y, m in months:
        try:
            download_seas51_monthly(
                _cds_client(), years=[y], leadtime="1", dirname=str(paths.downloads / "seas51"),
                pname=f"forecast_m1_{y}_{m:02d}_conus", months=[f"{m:02d}"],
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(f"SEAS5.1 {y}-{m:02d}: not available yet ({type(e).__name__}: {str(e)[:120]}); seas51 variants will be left out")
    return warnings


def monthly(paths: Paths, issue_date: date) -> list[str]:
    monthly_flow.download(paths.data / "metadata.csv", issue_date, paths.data / "test_monthly_naturalized_flow.csv")
    return []


# --- orchestration ---------------------------------------------------------------------------------------------------
SOURCES = {
    "snotel": snotel, "cdec": cdec, "usgs": usgs, "pdsi": pdsi, "usbr": usbr,
    "swann_daily": swann_daily, "swann_huc": swann_huc, "era5": era5_day, "seas51": seas51, "monthly": monthly,
}


def leakage_report(paths: Paths, issue_date: date) -> list[str]:
    """Input files carrying observations after the issue date (the engine also cuts there). The issue day's own SNOTEL / CDEC / USGS
    row is kept on purpose: the features need the row to exist but only read values lagged by >= 1 day."""
    cutoff, bad = pd.Timestamp(issue_date) + pd.Timedelta(days=1), []
    for sub, col in (("snotel", "date"), ("usgs_streamflow", "datetime")):
        for f in (paths.downloads / sub / f"FY{issue_date.year}").glob("*.csv"):
            d = pd.to_datetime(pd.read_csv(f)[col], utc=True).dt.tz_localize(None)
            if (d >= cutoff).any():
                bad.append(f"{sub}/{f.name}: rows after {issue_date}")
    mf = paths.data / "test_monthly_naturalized_flow.csv"
    if mf.exists():
        m = pd.read_csv(mf)
        if not all(monthly_flow._month_ended(int(y), int(mo), issue_date) for y, mo in zip(m.year, m.month)):
            bad.append("test_monthly_naturalized_flow.csv: months not complete before the issue date")
    return bad


def download(paths: Paths, issue_date: date, sources: list[str] | None = None, strict: bool = False) -> list[str]:
    """Fetch everything; returns warnings. A failing source is reported, not fatal, unless `strict` (the models degrade per variant)."""
    check_issue_date(issue_date)
    unknown = [n for n in sources or [] if n not in SOURCES]
    if unknown:
        raise ValueError(f"unknown source(s) {unknown}; choose from {sorted(SOURCES)}")
    paths.ensure()
    setup_data_dir(paths)
    os.environ["WSFR_DATA_ROOT"] = str(paths.data)  # wsfr_download resolves metadata.csv / cdec_snow_stations.csv from here
    engine.bootstrap(paths.src)  # vendored src.* (usbr, cds) are imported lazily by the sources
    warnings = []
    for name in sources or SOURCES:
        print(f"download {name}", flush=True)
        try:
            warnings += SOURCES[name](paths, issue_date)
        except Exception as e:  # noqa: BLE001
            if strict:
                raise
            warnings.append(f"{name}: download failed ({type(e).__name__}: {e})")
    leaks = leakage_report(paths, issue_date)
    if leaks:
        raise RuntimeError("data leakage past the issue date:\n  " + "\n  ".join(leaks))
    for w in warnings:
        print("WARNING", w, file=sys.stderr)
    return warnings
