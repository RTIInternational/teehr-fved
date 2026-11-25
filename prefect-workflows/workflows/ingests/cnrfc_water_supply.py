"""Ingest CNRFC water supply forecasts (ESP trend plots) and observations."""
from datetime import date, datetime
from pathlib import Path
from typing import Union
import logging

import pandas as pd
from prefect import flow, get_run_logger
from teehr.utils.utils import remove_dir_if_exists

from utils.cnrfc_utils import (
    CNRFC_TIME_ZONE,
    KAF_TO_CUBIC_METERS,
    LOCATION_ID_PREFIX,
    OBSERVED_TO_DATE,
    SEASONAL_PRODUCT_ID,
    WATER_YEAR_PRODUCT_ID,
    fetch_tabular_page,
    parse_tabular_page,
)
from utils import water_supply_utils
from utils.water_supply_utils import PRIMARY_COLUMNS, SECONDARY_COLUMNS
from workflows.utils.common_utils import (
    get_primary_location_ids,
    get_secondary_location_ids,
    initialize_evaluation,
)
from workflows.utils.time_utils import local_time_to_utc


logging.getLogger("teehr").setLevel(logging.INFO)

FORECAST_CONFIGURATION_NAME = "cnrfc_forecast"
OBSERVED_CONFIGURATION_NAME = "cnrfc_observed"
WY_VOLUME = "volume_1009_sum"
UNIT_NAME = "m^3"


def _to_utc(times: pd.Series) -> pd.Series:
    return local_time_to_utc(times, CNRFC_TIME_ZONE)


def format_forecasts(
    df: pd.DataFrame,
    variable_name: str,
    water_year: int,
    location_id: str,
) -> pd.DataFrame:
    """Format a trend table's forecasts as secondary timeseries.

    ``reference_time`` is the issue date and ``value_time`` is the start of the
    window, both local midnight converted to UTC. Issues after the window ends
    are dropped.
    """
    months = water_supply_utils.window_months(variable_name, water_year)
    members = [column for column in df.columns if column not in ("date", OBSERVED_TO_DATE)]
    df = (
        df[df["date"] < months[-1] + pd.offsets.MonthBegin(1)]
        .melt(id_vars="date", value_vars=members, var_name="member")
        .dropna(subset=["value"])
        .rename(columns={"date": "reference_time"})
    )
    df["reference_time"] = _to_utc(df["reference_time"])
    df["value_time"] = _to_utc(pd.Series(months[0], index=df.index))
    df["value"] = df["value"] * KAF_TO_CUBIC_METERS
    df["variable_name"] = variable_name
    df["configuration_name"] = FORECAST_CONFIGURATION_NAME
    df["unit_name"] = UNIT_NAME
    df["location_id"] = location_id
    return df[SECONDARY_COLUMNS]


def format_observations(
    df: pd.DataFrame,
    variable_name: str,
    water_year: int,
    location_id: str,
) -> pd.DataFrame:
    """Format a trend table's observed volume to date as primary timeseries.

    Writes the window total once the window is complete, and for seasonal
    windows the running total at the end of each completed month (as
    ``volume_{MMNN}_cumsum`` at the start of the next month). Newer tables
    start the accumulation a day late, so month ends are offset by the
    table's first observed date, capped at the end of the water year.
    """
    logger = get_run_logger()
    observed = df.dropna(subset=[OBSERVED_TO_DATE]).set_index("date")[OBSERVED_TO_DATE]
    if observed.empty:
        return pd.DataFrame(columns=PRIMARY_COLUMNS)
    months = water_supply_utils.window_months(variable_name, water_year)
    offset = observed.index.min() - months[0]
    if offset not in (pd.Timedelta(0), pd.Timedelta(days=1)):
        logger.warning(
            f"Skipping {location_id} {variable_name} observations for water year "
            f"{water_year}: accumulation starts {observed.index.min().date()}"
        )
        return pd.DataFrame(columns=PRIMARY_COLUMNS)
    water_year_end = pd.Timestamp(water_year, 9, 30)

    def observed_at_month_end(month: pd.Timestamp):
        row_date = min(month + pd.offsets.MonthEnd(0) + offset, water_year_end)
        return observed.get(row_date)

    rows = []
    total = observed_at_month_end(months[-1])
    if total is not None:
        rows.append((months[0], total, variable_name))
    if variable_name != WY_VOLUME:
        cumsum_variable_name = variable_name.replace("_sum", "_cumsum")
        for month in months:
            running_total = observed_at_month_end(month)
            if running_total is not None:
                rows.append((month + pd.offsets.MonthBegin(1), running_total, cumsum_variable_name))

    df = pd.DataFrame(rows, columns=["value_time", "value", "variable_name"])
    df["value_time"] = _to_utc(df["value_time"])
    df["value"] = df["value"] * KAF_TO_CUBIC_METERS
    df["reference_time"] = None
    df["configuration_name"] = OBSERVED_CONFIGURATION_NAME
    df["unit_name"] = UNIT_NAME
    df["location_id"] = location_id
    return df[PRIMARY_COLUMNS]


@flow(
    flow_run_name="ingest-cnrfc-water-supply",
    timeout_seconds=2 * 60 * 60
)
def ingest_cnrfc_water_supply(
    temp_dir_path: Union[str, Path],
    start_date: Union[str, date, datetime, None] = None,
    end_date: Union[str, date, datetime, None] = None,
    start_spark_cluster: bool = False,
) -> None:
    """CNRFC water supply forecast and observation ingest.

    Reads the seasonal (usually Apr-Jul) and water year ESP trend tables for
    whole water years, by default the previous and current ones, and upserts,
    so new issues and observations are picked up. Use an earlier
    ``start_date`` to backfill (tables start in water year 2011).
    """
    logger = get_run_logger()

    water_years = water_supply_utils.water_year_range(start_date, end_date)
    logger.info(f"Processing CNRFC water years {water_years[0]}-{water_years[-1]}")

    ev = initialize_evaluation(
        temp_dir_path=temp_dir_path,
        start_spark_cluster=start_spark_cluster,
        update_configs={
            "spark.sql.shuffle.partitions": "4"
        }
    )

    # Forecasts only for crosswalked stations, observations only for aliased
    # ones, so every row passes the warehouse location checks
    forecast_station_ids = get_secondary_location_ids(ev, LOCATION_ID_PREFIX)
    observed_station_ids = get_primary_location_ids(ev, LOCATION_ID_PREFIX)
    station_ids = sorted(set(forecast_station_ids) | set(observed_station_ids))
    if not station_ids:
        logger.warning("No CNRFC stations found in the location tables. Skipping.")
        ev.spark.stop()
        return
    logger.info(f"CNRFC forecast stations: {forecast_station_ids}")
    logger.info(f"CNRFC observation stations: {observed_station_ids}")

    cache_dir = Path(ev.cache_dir, "fetching", "cnrfc_water_supply")
    remove_dir_if_exists(cache_dir)

    # One water year at a time bounds memory for long backfills
    for water_year in water_years:
        forecasts, observations = [], []
        for station_id in station_ids:
            location_id = f"{LOCATION_ID_PREFIX}-{station_id}"
            for product_id in (SEASONAL_PRODUCT_ID, WATER_YEAR_PRODUCT_ID):
                variable_name, df = parse_tabular_page(
                    fetch_tabular_page(station_id, product_id, water_year)
                )
                if variable_name is None:
                    logger.info(
                        f"No CNRFC product {product_id} for {station_id} in water year {water_year}"
                    )
                    continue
                if station_id in forecast_station_ids:
                    forecasts.append(format_forecasts(df, variable_name, water_year, location_id))
                if station_id in observed_station_ids:
                    observations.append(format_observations(df, variable_name, water_year, location_id))
        timeseries = {
            table_name: pd.concat(dfs, ignore_index=True)
            for table_name, dfs in (
                ("secondary_timeseries", forecasts),
                ("primary_timeseries", observations),
            )
            if dfs
        }
        water_supply_utils.cache_water_year(cache_dir, water_year, timeseries)
        logger.info(f"✅ Cached CNRFC water year {water_year}")

    # Configurations and variables are added by warehouse/local/01_setup_local_warehouse.ipynb
    water_supply_utils.load_cached_timeseries(ev, cache_dir)
    logger.info("✅ Completed loading CNRFC water supply data into the warehouse")

    ev.spark.stop()
