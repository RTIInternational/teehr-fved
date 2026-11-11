"""Shared helpers for CDEC (California Data Exchange Center) ingests."""
from datetime import date
from io import StringIO
from typing import List

import pandas as pd
import requests
from prefect import task, get_run_logger

import teehr

from utils.water_supply_utils import AF_TO_CUBIC_METERS


CDEC_CSV_URL = "https://cdec.water.ca.gov/dynamicapp/req/CSVDataServlet"
LOCATION_ID_PREFIX = "cdec"
HTTP_TIMEOUT_SECONDS = (10, 120)  # (connect, read)
# CSVDataServlet reports local Pacific time (PST/PDT), despite the FAQ saying PST only
CDEC_TIME_ZONE = "America/Los_Angeles"

# CDEC units -> (TEEHR unit, conversion factor)
UNIT_CONVERSIONS = {
    "AF": ("m^3", AF_TO_CUBIC_METERS),
}


def get_cdec_station_ids(ev: teehr.Evaluation) -> List[str]:
    """CDEC station IDs crosswalked to a location, without the ``cdec-`` prefix."""
    crosswalks_df = ev.location_crosswalks.filter(
        {
            "column": "secondary_location_id",
            "operator": "like",
            "value": f"{LOCATION_ID_PREFIX}-%"
        }
    ).to_pandas()
    return sorted(
        crosswalks_df["secondary_location_id"].str.split("-", n=1).str[1].unique()
    )


@task(retries=2, retry_delay_seconds=30)
def fetch_cdec_csv(
    station_ids: List[str],
    sensor_nums: List[int],
    dur_code: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Fetch CDEC sensor data for several stations in one request.

    Returns columns ``station_id``, ``sensor_number``, ``date_time`` (naive
    local Pacific time, as CDEC reports it), ``value`` and ``units``. Missing
    values are dropped.
    """
    logger = get_run_logger()
    params = {
        "Stations": ",".join(station_ids),
        "SensorNums": ",".join(str(num) for num in sensor_nums),
        "dur_code": dur_code,
        "Start": start.strftime("%Y-%m-%d"),
        "End": end.strftime("%Y-%m-%d"),
    }
    logger.info(f"Fetching CDEC data: {params}")
    response = requests.get(CDEC_CSV_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text), dtype={"VALUE": str})
    df = pd.DataFrame({
        "station_id": df["STATION_ID"],
        "sensor_number": df["SENSOR_NUMBER"],
        "date_time": pd.to_datetime(df["DATE TIME"], format="%Y%m%d %H%M"),
        "value": pd.to_numeric(df["VALUE"], errors="coerce"),  # "---" is missing
        "units": df["UNITS"],
    })
    df = df.dropna(subset=["value"])
    logger.info(f"Fetched {len(df)} CDEC values")
    return df


def convert_cdec_units(df: pd.DataFrame) -> pd.DataFrame:
    """Convert ``value`` to SI and replace ``units`` with a ``unit_name`` column."""
    unknown = set(df["units"]) - set(UNIT_CONVERSIONS)
    if unknown:
        raise ValueError(f"Unexpected CDEC units: {unknown}")
    df = df.copy()
    df["value"] = df["value"] * df["units"].map(
        {units: factor for units, (_, factor) in UNIT_CONVERSIONS.items()}
    )
    df["unit_name"] = df["units"].map(
        {units: unit_name for units, (unit_name, _) in UNIT_CONVERSIONS.items()}
    )
    return df.drop(columns="units")
