"""Ingest NRCS AWDB streamflow forecasts and observations.

This workflow fetches both NRCS-adjusted forecast and observed SRVO (Snow Water
Equivalent) data from the NRCS AWDB REST API and loads it into the teehr warehouse.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

import teehr
from teehr.evaluation.spark_session_utils import create_spark_session

from utils import nrcs_utils
from workflows.utils.common_utils import initialize_evaluation


# Constants
DEFAULT_LOOKBACK_DAYS = 120
CONFIGURATION_NAME_FORECASTS = "nrcs_adjusted_forecast"
CONFIGURATION_NAME_OBSERVATIONS = "nrcs_adjusted_observed"
FAILURE_RATE_THRESHOLD = 0.5  # Allow up to 50% failure rate before failing workflow


@task(timeout_seconds=60 * 5, retries=2)
def _initialize_evaluation(
    temp_dir_path: Union[str, Path],
    start_spark_cluster: bool = False,
) -> teehr.RemoteReadWriteEvaluation:
    """Initialize Spark session and RemoteReadWriteEvaluation object."""
    logger = get_run_logger()
    logger.info(
        f"Initializing evaluation with temp_dir_path={temp_dir_path}, "
        f"start_spark_cluster={start_spark_cluster}"
    )

    ev = initialize_evaluation(
        temp_dir_path=temp_dir_path,
        start_spark_cluster=start_spark_cluster,
    )

    logger.info("✅ Evaluation initialized successfully")
    return ev


@task(timeout_seconds=60 * 5, retries=1)
def _get_nrcs_locations_observed(
    ev: teehr.RemoteReadWriteEvaluation,
) -> list[str]:
    """Query observed NRCS locations from location_id_aliases table."""
    logger = get_run_logger()

    try:
        locations_df = (
            ev.location_id_aliases.filter(
                filters=[
                    {"column": "location_id_alias", "operator": "like", "value": "nrcs-%"}
                ]
            )
            .to_pandas()
        )

        location_ids = locations_df["location_id_alias"].unique().tolist()
        logger.info(f"Found {len(location_ids)} NRCS observed locations")

        return location_ids
    except Exception as e:
        logger.warning(f"⚠️ Failed to query observed NRCS locations: {e}")
        return []


@task(timeout_seconds=60 * 5, retries=1)
def _get_nrcs_locations_forecast(
    ev: teehr.RemoteReadWriteEvaluation,
) -> list[str]:
    """Query forecast NRCS locations from location_crosswalks table."""
    logger = get_run_logger()

    try:
        crosswalks_df = (
            ev.location_crosswalks.filter(
                filters=[
                    {
                        "column": "secondary_location_id",
                        "operator": "like",
                        "value": "nrcs-%",
                    }
                ]
            )
            .to_pandas()
        )

        # Extract unique secondary location IDs and get their primary counterparts
        secondary_ids = crosswalks_df["secondary_location_id"].unique().tolist()
        logger.info(f"Found {len(secondary_ids)} NRCS forecast locations")

        return secondary_ids
    except Exception as e:
        logger.warning(f"⚠️ Failed to query forecast NRCS locations: {e}")
        return []


@task(cache_policy=NO_CACHE, retries=2, retry_delay_seconds=30, timeout_seconds=60 * 15)
def _fetch_nrcs_observations(
    location_ids: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch NRCS observations from API."""
    logger = get_run_logger()

    if not location_ids:
        logger.warning("⚠️ No location IDs provided for observations fetch")
        return pd.DataFrame()

    logger.info(
        f"Fetching NRCS observations for {len(location_ids)} locations, "
        f"period: {start_date} to {end_date}"
    )

    try:
        df = nrcs_utils.fetch_nrcs_observations(
            start_date=start_date,
            end_date=end_date,
            location_ids=location_ids,
        )
        logger.info(f"✅ Fetched {len(df)} observation records")
        return df
    except Exception as e:
        logger.error(f"❌ Failed to fetch observations: {e}")
        raise


@task(cache_policy=NO_CACHE, retries=2, retry_delay_seconds=30, timeout_seconds=60 * 15)
def _fetch_nrcs_forecasts(
    location_ids: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch NRCS forecasts from API."""
    logger = get_run_logger()

    if not location_ids:
        logger.warning("⚠️ No location IDs provided for forecasts fetch")
        return pd.DataFrame()

    logger.info(
        f"Fetching NRCS forecasts for {len(location_ids)} locations, "
        f"period: {start_date} to {end_date}"
    )

    try:
        df = nrcs_utils.fetch_nrcs_forecasts(
            start_date=start_date,
            end_date=end_date,
            location_ids=location_ids,
        )
        logger.info(f"✅ Fetched {len(df)} forecast records")
        return df
    except Exception as e:
        logger.error(f"❌ Failed to fetch forecasts: {e}")
        raise


@task(cache_policy=NO_CACHE)
def _validate_observations_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate observations DataFrame against schema."""
    logger = get_run_logger()

    if df.empty:
        logger.warning("⚠️ Observations DataFrame is empty")
        return df

    required_columns = ["location_id", "value_time", "value", "variable_name"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"Observations DataFrame missing required columns: {missing_columns}"
        )

    logger.info(
        f"✅ Observations validated: {len(df)} records, "
        f"columns: {list(df.columns)}"
    )
    return df


@task(cache_policy=NO_CACHE)
def _validate_forecasts_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate forecasts DataFrame against schema."""
    logger = get_run_logger()

    if df.empty:
        logger.warning("⚠️ Forecasts DataFrame is empty")
        return df

    required_columns = [
        "location_id",
        "reference_time",
        "value_time",
        "value",
        "variable_name",
        "member",
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"Forecasts DataFrame missing required columns: {missing_columns}"
        )

    logger.info(
        f"✅ Forecasts validated: {len(df)} records, "
        f"columns: {list(df.columns)}"
    )
    return df


@task(cache_policy=NO_CACHE)
def _load_to_warehouse_primary(
    ev: teehr.RemoteReadWriteEvaluation,
    df: pd.DataFrame,
) -> None:
    """Load observations to primary_timeseries table."""
    logger = get_run_logger()

    if df.empty:
        logger.warning("⚠️ Skipping load: observations DataFrame is empty")
        return

    try:
        logger.info(f"Loading {len(df)} observation records to primary_timeseries")
        ev.primary_timeseries.load_dataframe(df=df)
        logger.info("✅ Successfully loaded observations to primary_timeseries")
    except Exception as e:
        logger.error(f"❌ Failed to load observations: {e}")
        raise


@task(cache_policy=NO_CACHE)
def _load_to_warehouse_secondary(
    ev: teehr.RemoteReadWriteEvaluation,
    df: pd.DataFrame,
) -> None:
    """Load forecasts to secondary_timeseries table."""
    logger = get_run_logger()

    if df.empty:
        logger.warning("⚠️ Skipping load: forecasts DataFrame is empty")
        return

    try:
        logger.info(f"Loading {len(df)} forecast records to secondary_timeseries")
        ev.secondary_timeseries.load_dataframe(df=df)
        logger.info("✅ Successfully loaded forecasts to secondary_timeseries")
    except Exception as e:
        logger.error(f"❌ Failed to load forecasts: {e}")
        raise


@flow(
    flow_run_name="ingest-nrcs-streamflow-forecasts-observations",
    timeout_seconds=60 * 60,
)
def ingest_nrcs_streamflow_forecasts_observations(
    temp_dir_path: Union[str, Path],
    end_dt: Union[str, datetime, pd.Timestamp, None] = None,
    num_lookback_days: Union[int, None] = DEFAULT_LOOKBACK_DAYS,
    start_spark_cluster: bool = False,
    location_ids: Union[str, list[str], None] = None,
) -> None:
    """Ingest NRCS AWDB streamflow forecasts and observations.

    Fetches NRCS-adjusted forecast and observed SRVO (Snow Water Equivalent) data
    from the NRCS AWDB REST API within a flexible date window. Data is filtered to
    include only variables defined in nrcs_utils.NRCS_VARIABLE_MAPPING.

    Parameters
    ----------
    temp_dir_path : Union[str, Path]
        Working directory for Spark and cache storage
    end_dt : Union[str, datetime, pd.Timestamp, None], optional
        End of date window. If None, defaults to current UTC date.
        Can be a string (YYYY-MM-DD), datetime, or pandas Timestamp.
    num_lookback_days : Union[int, None], optional
        Number of days to look back from end_dt for start_dt.
        Default is 120 days (allows 1 month data posting delay).
        If None, no start_date limit is applied.
    start_spark_cluster : bool, optional
        Whether to start a Spark cluster. Default is False (local mode).
    location_ids : Union[str, list[str], None], optional
        Override location IDs for both observations and forecasts.
        If None, locations are queried dynamically from warehouse tables:
        - Observations from location_id_aliases table (prefix 'nrcs-')
        - Forecasts from location_crosswalks table (secondary_location_id prefix 'nrcs-')

    Returns
    -------
    None
    """
    logger = get_run_logger()
    logging.getLogger("teehr").setLevel(logging.INFO)

    ev = None
    try:
        logger.info(
            "🚀 Starting NRCS streamflow forecasts & observations ingest workflow"
        )

        # Initialize evaluation
        ev = _initialize_evaluation(
            temp_dir_path=temp_dir_path,
            start_spark_cluster=start_spark_cluster,
        )

        # Compute date window
        if isinstance(end_dt, str):
            end_dt = pd.Timestamp(end_dt)
        elif isinstance(end_dt, datetime) and not isinstance(end_dt, pd.Timestamp):
            end_dt = pd.Timestamp(end_dt)
        elif end_dt is None:
            end_dt = pd.Timestamp.utcnow().normalize()

        if num_lookback_days is None:
            start_dt = pd.Timestamp("1900-01-01")
        else:
            start_dt = end_dt - timedelta(days=num_lookback_days)

        start_date_str = start_dt.strftime("%Y-%m-%d")
        end_date_str = end_dt.strftime("%Y-%m-%d")

        logger.info(f"Date window: {start_date_str} to {end_date_str}")

        # Determine location IDs
        if location_ids is not None:
            if isinstance(location_ids, str):
                location_ids = [location_ids]
            logger.info(f"Using provided location_ids: {len(location_ids)} locations")
            obs_location_ids = location_ids
            forecast_location_ids = location_ids
        else:
            logger.info("Querying locations from warehouse tables...")
            obs_location_ids = _get_nrcs_locations_observed(ev)
            forecast_location_ids = _get_nrcs_locations_forecast(ev)

        # Fetch data
        obs_df = _fetch_nrcs_observations(
            location_ids=obs_location_ids,
            start_date=start_date_str,
            end_date=end_date_str,
        )

        forecast_df = _fetch_nrcs_forecasts(
            location_ids=forecast_location_ids,
            start_date=start_date_str,
            end_date=end_date_str,
        )

        # Validate DataFrames
        obs_df = _validate_observations_dataframe(obs_df)
        forecast_df = _validate_forecasts_dataframe(forecast_df)

        # Load to warehouse
        _load_to_warehouse_primary(ev, obs_df)
        _load_to_warehouse_secondary(ev, forecast_df)

        logger.info("✅ NRCS ingest workflow completed successfully")

    except Exception as e:
        logger.error(f"❌ NRCS ingest workflow failed: {e}")
        raise
    finally:
        if ev is not None:
            try:
                ev.spark.stop()
                logger.info("⏰ Spark session stopped")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping Spark: {e}")


__all__ = ["ingest_nrcs_streamflow_forecasts_observations"]
