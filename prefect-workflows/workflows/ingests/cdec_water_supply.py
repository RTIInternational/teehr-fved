"""Ingest CDEC water supply forecasts (Bulletin 120 and weekly updates) and observations."""
from datetime import date, datetime
from pathlib import Path
from typing import Union
import logging

import pandas as pd
from prefect import flow, get_run_logger
from teehr.fetching.utils import write_timeseries_parquet_file
from teehr.utils.utils import remove_dir_if_exists

from utils.cdec_utils import (
    LOCATION_ID_PREFIX,
    cdec_time_to_utc,
    convert_cdec_units,
    fetch_cdec_csv,
    get_cdec_station_ids,
)
from workflows.utils.common_utils import (
    initialize_evaluation,
    load_to_warehouse,
)


logging.getLogger("teehr").setLevel(logging.INFO)

FORECAST_CONFIGURATION_NAME = "cdec_forecast"
OBSERVED_CONFIGURATION_NAME = "cdec_observed"

AJ_VOLUME = "volume_0407_sum"
WY_VOLUME = "volume_1009_sum"
AJ_CUMULATIVE_VOLUME = "volume_0407_cumsum"
MONTHLY_VOLUME = "volume_monthly_sum"

# Seasonal volume -> (start month, number of months)
SEASONS = {
    AJ_VOLUME: (4, 4),
    WY_VOLUME: (10, 12),
}

# Forecast sensor -> (variable_name, member)
FORECAST_SENSORS = {
    260: (AJ_VOLUME, "p10"),
    261: (AJ_VOLUME, "p50"),
    262: (AJ_VOLUME, "p90"),
    263: (WY_VOLUME, "p10"),
    264: (WY_VOLUME, "p50"),
    265: (WY_VOLUME, "p90"),
}
MONTHLY_FNF_SENSOR = 65  # Monthly full natural flow (AF)

SECONDARY_COLUMNS = [
    "reference_time", "value_time", "value", "variable_name",
    "configuration_name", "unit_name", "location_id", "member",
]
PRIMARY_COLUMNS = SECONDARY_COLUMNS[:-1]


def _water_year(timestamp: Union[date, pd.Timestamp]) -> int:
    """Water year (Oct-Sep), named for the year it ends in."""
    return timestamp.year + 1 if timestamp.month >= 10 else timestamp.year


def _season_months(variable_name: str, water_year: int) -> pd.DatetimeIndex:
    """Month starts of a seasonal volume window in a water year."""
    start_month, num_months = SEASONS[variable_name]
    start_year = water_year - 1 if start_month >= 10 else water_year
    return pd.date_range(pd.Timestamp(start_year, start_month, 1), periods=num_months, freq="MS")


def format_forecasts(df: pd.DataFrame) -> pd.DataFrame:
    """Format forecast sensors as secondary timeseries.

    ``reference_time`` is the issue date and ``value_time`` is the start of the
    forecast window, so lead time shrinks across reissues. Both are local
    midnight converted to UTC.
    """
    # Some issues are stamped 01:00; keep the date only
    df = df.assign(reference_time=df["date_time"].dt.normalize())
    df = df.drop_duplicates(
        subset=["station_id", "sensor_number", "reference_time"], keep="last"
    )
    df["variable_name"] = df["sensor_number"].map(lambda num: FORECAST_SENSORS[num][0])
    df["member"] = df["sensor_number"].map(lambda num: FORECAST_SENSORS[num][1])
    df["value_time"] = [
        _season_months(variable_name, _water_year(reference_time))[0]
        for variable_name, reference_time in zip(df["variable_name"], df["reference_time"])
    ]
    df["reference_time"] = cdec_time_to_utc(df["reference_time"])
    df["value_time"] = cdec_time_to_utc(df["value_time"])
    df["configuration_name"] = FORECAST_CONFIGURATION_NAME
    df["location_id"] = f"{LOCATION_ID_PREFIX}-" + df["station_id"]
    return convert_cdec_units(df)[SECONDARY_COLUMNS]


def _seasonal_volumes(monthly_df: pd.DataFrame, water_year: int) -> pd.DataFrame:
    """Seasonal sums for complete seasons, and the Apr-Jul running total for completed months."""
    rows = []
    for location_id, location_volumes in monthly_df.groupby("location_id"):
        by_month = location_volumes.set_index("value_time")["value"]
        for variable_name in SEASONS:
            months = _season_months(variable_name, water_year)
            if months.isin(by_month.index).all():
                rows.append((location_id, months[0], by_month[months].sum(), variable_name))
        running_total = 0.0
        for month in _season_months(AJ_VOLUME, water_year):
            if month not in by_month.index:
                break
            running_total += by_month[month]
            rows.append((location_id, month + pd.offsets.MonthBegin(1), running_total, AJ_CUMULATIVE_VOLUME))
    return pd.DataFrame(
        rows, columns=["location_id", "value_time", "value", "variable_name"]
    ).astype({"value_time": "datetime64[ns]", "value": float}).assign(unit_name="m^3")


def format_observations(df: pd.DataFrame, water_year: int) -> pd.DataFrame:
    """Format monthly volumes as primary timeseries, plus derived seasonal volumes."""
    monthly_df = convert_cdec_units(df).assign(
        location_id=f"{LOCATION_ID_PREFIX}-" + df["station_id"],
        value_time=df["date_time"].dt.normalize(),
        variable_name=MONTHLY_VOLUME,
    )
    df = pd.concat([monthly_df, _seasonal_volumes(monthly_df, water_year)], ignore_index=True)
    df["value_time"] = cdec_time_to_utc(df["value_time"])
    df["reference_time"] = None
    df["configuration_name"] = OBSERVED_CONFIGURATION_NAME
    return df[PRIMARY_COLUMNS]


@flow(
    flow_run_name="ingest-cdec-water-supply",
    timeout_seconds=60 * 60
)
def ingest_cdec_water_supply(
    temp_dir_path: Union[str, Path],
    start_date: Union[str, date, datetime, None] = None,
    end_date: Union[str, date, datetime, None] = None,
    start_spark_cluster: bool = False,
) -> None:
    """CDEC water supply forecast and observation ingest.

    Fetches whole water years (Oct-Sep), by default from the start of the
    previous water year through today, and upserts, so revised forecasts and
    observations are picked up. Use an earlier ``start_date`` to backfill.
    """
    logger = get_run_logger()

    # Evaluated at flow run time, not deployment time
    last_water_year = _water_year(pd.Timestamp(end_date or date.today()))
    if start_date is None:
        first_water_year = last_water_year - 1
    else:
        first_water_year = _water_year(pd.Timestamp(start_date))
    logger.info(f"Processing CDEC water years {first_water_year}-{last_water_year}")

    ev = initialize_evaluation(
        temp_dir_path=temp_dir_path,
        start_spark_cluster=start_spark_cluster,
        update_configs={
            "spark.sql.shuffle.partitions": "4"
        }
    )

    station_ids = get_cdec_station_ids(ev)
    if not station_ids:
        logger.warning("No CDEC stations found in the location crosswalks. Skipping.")
        ev.spark.stop()
        return
    logger.info(f"CDEC stations: {station_ids}")

    cache_dir = Path(ev.cache_dir, "fetching", "cdec_water_supply")
    remove_dir_if_exists(cache_dir)

    # One water year at a time bounds memory and request size for long backfills.
    # Stations without a sensor (e.g. POH has no monthly full natural flow) return no rows.
    for water_year in range(first_water_year, last_water_year + 1):
        start = date(water_year - 1, 10, 1)
        end = date(water_year, 9, 30)
        timeseries = {
            "secondary_timeseries": format_forecasts(
                fetch_cdec_csv(station_ids, list(FORECAST_SENSORS), "E", start, end)
            ),
            "primary_timeseries": format_observations(
                fetch_cdec_csv(station_ids, [MONTHLY_FNF_SENSOR], "M", start, end),
                water_year=water_year,
            ),
        }
        for table_name, df in timeseries.items():
            if df.empty:
                continue
            table_dir = Path(cache_dir, table_name)
            table_dir.mkdir(parents=True, exist_ok=True)
            write_timeseries_parquet_file(
                filepath=Path(table_dir, f"wy{water_year}.parquet"),
                overwrite_output=True,
                data=df,
                timeseries_type=table_name.split("_")[0],
            )
        logger.info(f"✅ Cached CDEC water year {water_year}")

    # Configurations and variables are added by warehouse/local/01_setup_local_warehouse.ipynb
    for table_name in ("secondary_timeseries", "primary_timeseries"):
        table_dir = Path(cache_dir, table_name)
        if not any(table_dir.glob("*.parquet")):
            logger.info(f"No {table_name} data cached. Skipping load.")
            continue
        load_to_warehouse(
            ev=ev,
            in_path=table_dir,
            table_name=table_name,
            write_mode="upsert",
        )
    logger.info("✅ Completed loading CDEC water supply data into the warehouse")

    ev.spark.stop()
