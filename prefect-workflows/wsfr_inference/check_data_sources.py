#!/usr/bin/env python3
"""Probe shared external data-source endpoints for all three WSF models.

Requires only Python 3 and requests. Probes make small read-only requests; they
check reachability and basic response shape, not credentials or full downloads.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import io
import json
import sys
from typing import Callable

import requests


MODELS = "1st, 2nd, 3rd"
TIMEOUT_SECONDS = 30
USER_AGENT = "WSFR-data-source-firewall-check/1.0"


@dataclass(frozen=True)
class Probe:
    name: str
    models: str
    method: str
    url: str
    params: dict | None = None
    data: dict | None = None
    validator: Callable[[requests.Response], None] | None = None
    stream: bool = False


def require_json_object(response: requests.Response) -> None:
    if not isinstance(response.json(), dict):
        raise ValueError("expected a JSON object")


def require_awdb_data(response: requests.Response) -> None:
    payload = response.json()
    if not isinstance(payload, list) or not payload or "data" not in payload[0]:
        raise ValueError("unexpected AWDB response shape")


def require_cdec_json(response: requests.Response) -> None:
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("expected a JSON array from CDEC")


def require_acis_data(response: requests.Response) -> None:
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload:
        raise ValueError("unexpected ACIS response shape")


def require_snowview_columns(response: requests.Response) -> None:
    rows = csv.reader(line for line in io.StringIO(response.text) if not line.lstrip().startswith("#"))
    header = next((set(cell.strip() for cell in row) for row in rows if row), set())
    required = {"date", "overall_mean_swe_in", "overall_cumulative_precip_in"}
    if not required.issubset(header):
        raise ValueError(f"CSV header missing {sorted(required - header)}")


def build_probes(today: date | None = None) -> list[Probe]:
    today = today or date.today()
    recent_start = (today - timedelta(days=10)).isoformat()
    recent_end = today.isoformat()
    # Match the model's source check: stable SWANN data is sampled ~300 days back.
    sample_day = today - timedelta(days=300)
    water_year = sample_day.year + (sample_day.month >= 10)
    sample_date = sample_day.strftime("%Y%m%d")

    return [
        Probe(
            "NRCS AWDB REST (SNOTEL and monthly flow)", MODELS, "GET",
            "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data",
            params={
                "stationTriplets": "1005:CO:SNTL", "elements": "WTEQ",
                "duration": "DAILY", "beginDate": recent_start, "endDate": recent_end,
            }, validator=require_awdb_data,
        ),
        Probe(
            "NRCS AWDB SOAP WSDL (station metadata)", "1st, 2nd", "GET",
            "https://wcc.sc.egov.usda.gov/awdbWebService/services?WSDL",
            stream=True,
        ),
        Probe(
            "USGS NWIS daily values", MODELS, "GET",
            "https://waterservices.usgs.gov/nwis/dv/",
            params={"format": "json", "sites": "12362500", "parameterCd": "00060", "period": "P7D"},
            validator=require_json_object,
        ),
        Probe(
            "CDEC daily sensor data", "1st, 3rd", "GET",
            "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet",
            params={
                "Stations": "AGP", "dur_code": "d", "SensorNums": "82",
                "Start": recent_start, "End": recent_end,
            }, validator=require_cdec_json,
        ),
        Probe(
            "NWRFC monthly natural flow", MODELS, "GET",
            "https://www.nwrfc.noaa.gov/natural/nat_norm_text.cgi",
            params={"id": "RODW1"},
        ),
        Probe(
            "ACIS MultiStnData", "1st", "POST",
            "https://data.rcc-acis.org/MultiStnData",
            data={"params": json.dumps({
                "basin": "10030101", "sdate": recent_start, "edate": recent_end,
                "meta": "name, sids", "elems": [
                    {"name": "pcpn", "interval": "dly", "duration": 1,
                     "reduce": {"reduce": "sum"}, "maxmissing": 3},
                    {"name": "maxt", "interval": "dly", "duration": 1,
                     "reduce": {"reduce": "sum"}, "maxmissing": 3},
                ],
            })}, validator=require_acis_data,
        ),
        Probe(
            "UA SnowView HUC CSV", "1st, 3rd", "GET",
            "https://snowview.arizona.edu/csv/Download/Watersheds/100301.csv",
            validator=require_snowview_columns,
        ),
        Probe(
            "UA SWANN daily NetCDF", "1st, 3rd", "GET",
            "https://climate.arizona.edu/data/UA_SWE/DailyData_4km/"
            f"WY{water_year}/UA_SWE_Depth_4km_v1_{sample_date}_stable.nc",
            stream=True,
        ),
        Probe(
            "gridMET PDSI THREDDS", "3rd", "GET",
            "https://thredds.northwestknowledge.net/thredds/ncss/"
            "agg_met_pdsi_1979_CurrentYear_CONUS.nc",
            params={
                "var": "daily_mean_palmer_drought_severity_index",
                "disableLLSubset": "on", "disableProjSubset": "on",
                "horizStride": "1", "time_start": f"{recent_start}T00:00:00Z",
                "time_end": f"{recent_start}T00:00:00Z", "timeStride": "1",
                "accept": "netcdf",
            }, stream=True,
        ),
        Probe(
            "USBR RISE inflow CSV", "3rd", "GET",
            "https://data.usbr.gov/rise/api/result/download",
            params={
                "type": "csv", "itemId": "10773", "after": recent_start,
                "before": recent_end, "order": "ASC",
            }, stream=True,
        ),
        Probe(
            "Copernicus CDS ERA5-Land catalogue", "3rd", "GET",
            "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/"
            "reanalysis-era5-land",
            validator=require_json_object,
        ),
        Probe(
            "Copernicus CDS SEAS5.1 catalogue", "3rd", "GET",
            "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/"
            "seasonal-monthly-single-levels",
            validator=require_json_object,
        ),
    ]


def run_probe(session: requests.Session, probe: Probe, timeout: int) -> tuple[bool, str]:
    response = None
    try:
        headers = {"User-Agent": USER_AGENT}
        if probe.stream:
            headers["Range"] = "bytes=0-0"
        response = session.request(
            probe.method, probe.url, params=probe.params, data=probe.data,
            headers=headers, timeout=timeout, allow_redirects=True, stream=probe.stream,
        )
        if response.status_code not in (200, 206):
            return False, f"HTTP {response.status_code} (endpoint responded; check status/allowlist)"
        if probe.validator:
            probe.validator(response)
        return True, f"HTTP {response.status_code}"
    except requests.RequestException as error:
        return False, f"{type(error).__name__}: {error}"
    except (ValueError, KeyError, IndexError, json.JSONDecodeError) as error:
        return False, f"HTTP {response.status_code}; response check failed: {error}"
    finally:
        if response is not None:
            response.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help="per-request timeout in seconds")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    failures = 0
    with requests.Session() as session:
        for probe in build_probes():
            ok, detail = run_probe(session, probe, args.timeout)
            status = "PASS" if ok else "FAIL"
            print(f"{status:4} {probe.models:10} {probe.name}: {detail}")
            failures += not ok
    print(f"\n{len(build_probes()) - failures}/{len(build_probes())} data-source probes passed")
    if failures:
        print("An HTTP response confirms the endpoint was reached, even if its status or payload check failed.")
    print("CDS probes check public catalogues only; they do not validate credentials or file-download redirects.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
