"""`check-sources`: ping every external endpoint the package uses and verify the response still has the shape the code relies on.

Small requests only (nothing is written). Run it before scheduling a forecast, or from a monitor, to catch the kind of drift that broke the
competition-era downloaders (moved hosts, renamed columns, new file suffixes). Exit code 1 if any probe fails; `warn` means reachable but
older than expected.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd
import requests

from . import monthly_flow

TIMEOUT = 30
AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"

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


PROBES = {"awdb_snotel": awdb_snotel, "awdb_srvo": awdb_srvo, "nwrfc_skagit": nwrfc_skagit, "nwis": nwis}


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
