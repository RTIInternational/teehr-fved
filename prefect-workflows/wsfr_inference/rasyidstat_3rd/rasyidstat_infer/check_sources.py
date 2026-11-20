"""`check-sources`: ping every external endpoint the package uses and verify the response still has the shape the code relies on.

Small requests only (nothing is written). Run it before scheduling a forecast, or from a monitor, to catch the kind of drift that broke the
competition-era downloaders (moved hosts, renamed columns, new file suffixes). Exit code 1 if any probe fails; `warn` means reachable but
older than expected.
"""

from __future__ import annotations

import io
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import download, monthly_flow

TIMEOUT = 30
AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
CDEC = "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet"
RISE = "https://data.usbr.gov/rise/api/result/download"
PDSI = (
    "https://thredds.northwestknowledge.net/thredds/ncss/agg_met_pdsi_1979_CurrentYear_CONUS.nc"
    "?var=daily_mean_palmer_drought_severity_index&disableLLSubset=on&disableProjSubset=on&horizStride=1"
    "&time_start={d}T00%3A00%3A00Z&time_end={d}T00%3A00%3A00Z&timeStride=1&accept=netcdf"
)
CDS_CATALOGUE = "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/{ds}"

OK, WARN, FAIL = "ok", "warn", "fail"


def _age_status(newest: pd.Timestamp | None, today: date, max_age_days: int) -> tuple[str, str]:
    if newest is None or pd.isna(newest):
        return FAIL, "no data returned"
    age = (pd.Timestamp(today) - pd.Timestamp(newest)).days
    return (OK if age <= max_age_days else WARN), f"newest observation {pd.Timestamp(newest).date()} ({age} d old)"


def awdb_snotel(today: date):
    r = requests.get(
        AWDB, timeout=TIMEOUT,
        params=dict(stationTriplets="1005:CO:SNTL", elements="WTEQ", duration="DAILY", beginDate=(today - timedelta(days=10)).isoformat(), endDate=today.isoformat()),
    )
    r.raise_for_status()
    values = r.json()[0]["data"][0]["values"]
    assert {"date", "value"} <= set(values[0]), f"unexpected keys {sorted(values[0])}"
    return _age_status(pd.to_datetime(max(v["date"] for v in values if v.get("value") is not None)), today, 4)


def awdb_srvo(today: date):
    df = monthly_flow.fetch_awdb("12362500:MT:USGS", monthly_flow.forecast_year(today), today)
    return (OK if not df.empty else FAIL), f"{len(df)} monthly SRVO values for hungry_horse"


def nwrfc_skagit(today: date):
    df = monthly_flow.fetch_nwrfc("RODW1", monthly_flow.forecast_year(today))
    return (OK if not df.empty else FAIL), f"{len(df)} monthly values for RODW1"


def cdec(today: date):
    r = requests.get(
        CDEC, timeout=TIMEOUT,
        params=dict(Stations="AGP", dur_code="d", SensorNums="82", Start=(today - timedelta(days=10)).isoformat(), End=today.isoformat()),
    )
    r.raise_for_status()
    df = pd.json_normalize(r.json())
    if df.empty:
        return WARN, "reachable, no rows for AGP sensor 82"
    assert {"stationId", "date", "value"} <= set(df.columns), f"unexpected columns {sorted(df.columns)}"
    return _age_status(pd.to_datetime(df["date"]).max(), today, 4)


def nwis(today: date):
    from dataretrieval import waterdata

    frame, _ = waterdata.get_daily(
        monitoring_location_id="USGS-12362500", parameter_code="00060", statistic_id="00003",
        time=f"{(today - timedelta(days=7)).isoformat()}/{today.isoformat()}",
    )
    if frame.empty:
        return FAIL, "no data returned"
    usable = pd.to_numeric(frame["value"], errors="coerce").notna()
    newest = pd.to_datetime(frame.loc[usable, "time"], utc=True).max()
    return _age_status(newest.tz_localize(None) if pd.notna(newest) else None, today, 3)


def rise(today: date):
    r = requests.get(
        RISE, timeout=TIMEOUT,
        params=dict(type="csv", itemId="10773", after=(today - timedelta(days=10)).isoformat(), before=today.isoformat(), order="ASC"),
    )
    r.raise_for_status()
    assert "Lake/Reservoir Inflow" in r.text, "inflow parameter name not found in the RISE CSV"
    return OK, "inflow rows for item 10773"


def pdsi(today: date):
    d = today - timedelta(days=30)
    r = requests.get(PDSI.format(d=d.isoformat()), timeout=TIMEOUT * 2)
    r.raise_for_status()
    return (OK if r.content[:3] == b"CDF" or r.content[:4] == b"\x89HDF" else FAIL), f"NetCDF subset for {d}"


def swann_daily(today: date):
    """The file suffix tier depends on the age of the day; one probe per tier."""
    found = []
    for age, tier in ((3, "early"), (60, "provisional"), (300, "stable")):
        day = today - timedelta(days=age)
        wy = day.year + (day.month >= 10)
        url = download.SWANN_URL.format(wy=wy, day=day.strftime("%Y%m%d"), tier=tier)
        status = requests.head(url, timeout=TIMEOUT, allow_redirects=True).status_code
        found.append(f"{tier}:{status}")
        if status != 200 and tier != "early":  # the early tier only exists for the current month
            return FAIL, ", ".join(found) + f" ({url})"
    return OK, ", ".join(found)


def snowview_huc(today: date):
    r = requests.get(download.SNOWVIEW_URL.format(huc="100301"), timeout=TIMEOUT * 2)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), comment="#")
    need = {"date", *download.HUC_RENAME}
    if not need <= set(df.columns):
        return FAIL, f"columns changed: missing {sorted(need - set(df.columns))}, have {list(df.columns)}"
    return _age_status(pd.to_datetime(df["date"]).max(), today, 6)


def cds(today: date):
    if not (Path.home() / ".cdsapirc").exists():
        return FAIL, "~/.cdsapirc missing"
    out = []
    for ds in ("reanalysis-era5-land", "seasonal-monthly-single-levels"):
        r = requests.get(CDS_CATALOGUE.format(ds=ds), timeout=TIMEOUT)
        out.append(f"{ds}:{r.status_code}")
        if r.status_code != 200:
            return FAIL, ", ".join(out)
    return OK, ", ".join(out) + " (credentials not exercised)"


PROBES = {
    "awdb_snotel": awdb_snotel, "awdb_srvo": awdb_srvo, "nwrfc_skagit": nwrfc_skagit, "cdec": cdec, "nwis": nwis, "rise": rise,
    "pdsi": pdsi, "swann_daily": swann_daily, "snowview_huc": snowview_huc, "cds": cds,
}


def check_sources(today: date | None = None, only: list[str] | None = None) -> list[tuple[str, str, str, float]]:
    today = today or date.today()
    results = []
    for name in only or PROBES:
        t0 = time.time()
        try:
            status, detail = PROBES[name](today)
        except Exception as e:  # noqa: BLE001
            status, detail = FAIL, f"{type(e).__name__}: {str(e)[:200]}"
        results.append((name, status, detail, time.time() - t0))
    return results


def report(results) -> int:
    for name, status, detail, secs in results:
        print(f"{status.upper():5} {name:14} {secs:5.1f}s  {detail}")
    failed = [r[0] for r in results if r[1] == FAIL]
    print("OK" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0
