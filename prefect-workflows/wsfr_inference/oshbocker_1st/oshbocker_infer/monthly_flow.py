"""Monthly naturalized flow ("variant A") for the forecast year, in the competition's test-file schema:
test_monthly_naturalized_flow.csv = site_id, forecast_year, year, month, volume (KAF).

Sources (the competition's monthly flow is the NRCS-adjusted series; validated 2019-2023 against the
competition files: 96% exact, Skagit exact):
  * NRCS AWDB element SRVO, via the site's `nrcs_id` triplet in metadata.csv (22 sites)
  * NWRFC natural flow `nat_norm_text.cgi?id=<rfc_id>` for sites with no NRCS id on the NWRFC (Skagit, RODW1)
  * San Joaquin, Merced and American River have no monthly flow (as in the competition files).

Only months that ended before the issue date are written: a partial current month would be a leak of the very
quantity being forecast and a biased input.
"""

from __future__ import annotations

import io
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
NWRFC = "https://www.nwrfc.noaa.gov/natural/nat_norm_text.cgi"
COLUMNS = ["site_id", "forecast_year", "year", "month", "volume"]
NWRFC_ATTEMPTS = 4
NWRFC_BACKOFF_S = 5


def forecast_year(issue_date: date) -> int:
    return issue_date.year if issue_date.month < 10 else issue_date.year + 1


def _month_ended(year: int, month: int, issue_date: date) -> bool:
    first_of_next = date(year + (month == 12), month % 12 + 1, 1)
    return first_of_next <= issue_date


def fetch_awdb(triplet: str, fy: int, issue_date: date) -> pd.DataFrame:
    r = requests.get(
        AWDB,
        params=dict(stationTriplets=triplet, elements="SRVO", duration="MONTHLY", beginDate=f"{fy - 1}-10-01", endDate=issue_date.isoformat()),
        timeout=60,
    )
    r.raise_for_status()
    rows = [
        (v["year"], v["month"], v["value"] / 1000.0)  # ac-ft -> KAF
        for station in r.json()
        for el in station.get("data", [])
        for v in el.get("values", [])
        if v.get("value") is not None
    ]
    return pd.DataFrame(rows, columns=["year", "month", "volume"])


def fetch_nwrfc(rfc_id: str, fy: int) -> pd.DataFrame:
    for attempt in range(1, NWRFC_ATTEMPTS + 1):
        try:
            r = requests.get(NWRFC, params=dict(id=rfc_id), timeout=60)
            r.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as error:
            if isinstance(error, requests.HTTPError) and (
                error.response is None or error.response.status_code not in (429, 500, 502, 503, 504)
            ):
                raise
            if attempt == NWRFC_ATTEMPTS:
                raise
            wait = NWRFC_BACKOFF_S * attempt
            print(f"WARNING NWRFC {rfc_id}: {error}; retrying in {wait}s (attempt {attempt}/{NWRFC_ATTEMPTS})", file=sys.stderr)
            time.sleep(wait)
    lines = [ln for ln in r.text.replace("<br>", "\n").splitlines() if ln.startswith(rfc_id + ",") or ln.startswith("ID,")]
    wide = pd.read_csv(io.StringIO("\n".join(lines)))
    long = wide.melt(id_vars=["ID", "Calendar Year"], var_name="mon", value_name="volume").dropna(subset=["volume"])
    long["month"] = pd.to_datetime(long["mon"], format="%b").dt.month
    long["year"] = long["Calendar Year"]
    keep = ((long.year == fy - 1) & (long.month >= 10)) | ((long.year == fy) & (long.month <= 9))
    return long.loc[keep, ["year", "month", "volume"]]


def fetch(metadata_csv: Path, issue_date: date) -> pd.DataFrame:
    fy = forecast_year(issue_date)
    frames = []
    for _, row in pd.read_csv(metadata_csv).iterrows():
        if isinstance(row.nrcs_id, str) and row.nrcs_id.strip():
            df = fetch_awdb(row.nrcs_id.strip(), fy, issue_date)
        elif row.get("rfc") == "NWRFC" and isinstance(row.rfc_id, str):
            df = fetch_nwrfc(row.rfc_id, fy)
        else:
            continue
        df = df[[_month_ended(int(y), int(m), issue_date) for y, m in zip(df.year, df.month)]]
        if df.empty:
            print(f"WARNING monthly flow: no complete months for {row.site_id} FY{fy}", file=sys.stderr)
            continue
        frames.append(df.assign(site_id=row.site_id, forecast_year=fy))
    if not frames:
        raise RuntimeError("no monthly flow could be downloaded")
    return pd.concat(frames, ignore_index=True)[COLUMNS]


def expected_months(issue_date: date) -> list[tuple[int, int]]:
    fy = forecast_year(issue_date)
    months = [(fy - 1, m) for m in (10, 11, 12)] + [(fy, m) for m in range(1, 10)]
    return [(y, m) for y, m in months if _month_ended(y, m, issue_date)]


def download(metadata_csv: Path, issue_date: date, out_csv: Path) -> pd.DataFrame:
    """Write `out_csv`; warn for every site that lacks any month ended before the issue date."""
    df = fetch(metadata_csv, issue_date)
    need = set(expected_months(issue_date))
    for site, g in df.groupby("site_id"):
        missing = sorted(need - set(zip(g.year, g.month)))
        if missing:
            print(f"WARNING monthly flow: {site} missing {len(missing)} month(s), latest expected {max(need)}: {missing[:3]}...", file=sys.stderr)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df
