"""Ingest NRCS AWDB streamflow forecasts and observations (v2 - per-location processing).

This workflow processes each location sequentially:
1. Fetch location's observations and forecasts
2. Identify unique full forecast periods for the location
3. Generate cumsum observations (only for period months)
4. Extract final observed values from cumsum
5. Process forecasts with Cases A/B/C retagging and reconstruction
6. Write all locations' combined data to warehouse
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

from utils import nrcs_utils_v2 as nrcs_utils
from workflows.utils.common_utils import initialize_evaluation


# Constants
DEFAULT_LOOKBACK_DAYS = 120
CONFIGURATION_NAME_FORECASTS = "nrcs_adjusted_forecast"
CONFIGURATION_NAME_OBSERVATIONS = "nrcs_adjusted_observed"


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

        secondary_ids = crosswalks_df["secondary_location_id"].unique().tolist()
        logger.info(f"Found {len(secondary_ids)} NRCS forecast locations")

        return secondary_ids
    except Exception as e:
        logger.warning(f"⚠️ Failed to query forecast NRCS locations: {e}")
        return []


@task(cache_policy=NO_CACHE, retries=2, retry_delay_seconds=30, timeout_seconds=60 * 15)
def _fetch_nrcs_observations(
    location_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch NRCS observations for a single location from API."""
    logger = get_run_logger()

    try:
        df = nrcs_utils.fetch_nrcs_observations(
            start_date=start_date,
            end_date=end_date,
            location_ids=location_id,
        )
        logger.info(f"✅ Fetched {len(df)} observation records for {location_id}")
        return df
    except Exception as e:
        logger.error(f"❌ Failed to fetch observations for {location_id}: {e}")
        return pd.DataFrame()


@task(cache_policy=NO_CACHE, retries=2, retry_delay_seconds=30, timeout_seconds=60 * 15)
def _fetch_nrcs_forecasts(
    location_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch NRCS forecasts for a single location from API."""
    logger = get_run_logger()

    try:
        df = nrcs_utils.fetch_nrcs_forecasts(
            start_date=start_date,
            end_date=end_date,
            location_ids=location_id,
        )
        logger.info(f"✅ Fetched {len(df)} forecast records for {location_id}")
        return df
    except Exception as e:
        logger.error(f"❌ Failed to fetch forecasts for {location_id}: {e}")
        return pd.DataFrame()


def _process_location(
    location_id: str,
    obs_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process a single location's observations and forecasts.
    
    Returns tuple of (combined_obs_df, forecast_df) where obs_df includes
    raw observations, cumsum observations, and final observed values.
    """
    logger = get_run_logger()
    
    # Skip if either dataset is empty
    if obs_df.empty or forecast_df.empty:
        logger.warning(f"⚠️ Skipping {location_id}: obs={len(obs_df)}, fcst={len(forecast_df)}")
        return obs_df, forecast_df
    
    # Identify unique full forecast periods for this location
    periods = nrcs_utils._identify_forecast_periods_per_location(forecast_df)
    location_periods = periods.get(location_id, [])
    
    if not location_periods:
        logger.warning(f"⚠️ No forecast periods identified for {location_id}")
        return obs_df, forecast_df
    
    logger.info(f"Found periods for {location_id}: {location_periods}")
    
    # Generate cumsum observations (only for period months)
    cumsum_obs_df = nrcs_utils._generate_observed_cumsum_v2(
        location_obs_df=obs_df,
        periods=location_periods,
        location_id=location_id,
    )
    
    if not cumsum_obs_df.empty:
        logger.info(f"Generated {len(cumsum_obs_df)} cumsum observations for {location_id}")
        obs_df = pd.concat([obs_df, cumsum_obs_df], ignore_index=True)
    
    # Extract final observed values from cumsum
    final_obs_df = nrcs_utils._extract_final_observed_from_cumsum(
        location_cumsum_df=cumsum_obs_df,
        periods=location_periods,
        location_id=location_id,
    )
    
    if not final_obs_df.empty:
        logger.info(f"Generated {len(final_obs_df)} final observed values for {location_id}")
        obs_df = pd.concat([obs_df, final_obs_df], ignore_index=True)
    
    # Process forecasts with Cases A/B/C logic
    processed_forecast_df = nrcs_utils._process_location_forecasts(
        location_forecasts_df=forecast_df,
        location_cumsum_df=cumsum_obs_df,
        periods=location_periods,
        location_id=location_id,
    )
    
    if not processed_forecast_df.empty:
        logger.info(f"Processed {len(processed_forecast_df)} forecasts for {location_id}")
        forecast_df = pd.concat([forecast_df, processed_forecast_df], ignore_index=True)
    
    return obs_df, forecast_df


@task(cache_policy=NO_CACHE, timeout_seconds=60 * 60)
def _process_all_locations(
    location_ids: list[str],
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process all locations sequentially.
    
    Returns combined obs_df and forecast_df for all locations.
    """
    logger = get_run_logger()
    
    all_obs = []
    all_forecasts = []
    
    for idx, location_id in enumerate(location_ids, 1):
        logger.info(f"Processing location {idx}/{len(location_ids)}: {location_id}")
        
        # Fetch data for this location
        obs_df = _fetch_nrcs_observations(location_id, start_date, end_date)
        forecast_df = _fetch_nrcs_forecasts(location_id, start_date, end_date)
        
        if obs_df.empty or forecast_df.empty:
            logger.warning(f"⚠️ Skipping {location_id}: insufficient data")
            continue
        
        # Process this location
        processed_obs, processed_forecast = _process_location(
            location_id=location_id,
            obs_df=obs_df,
            forecast_df=forecast_df,
        )
        
        all_obs.append(processed_obs)
        all_forecasts.append(processed_forecast)
    
    # Combine all locations
    combined_obs_df = (
        pd.concat(all_obs, ignore_index=True) if all_obs else pd.DataFrame()
    )
    combined_forecast_df = (
        pd.concat(all_forecasts, ignore_index=True) if all_forecasts else pd.DataFrame()
    )
    
    logger.info(
        f"Combined results: {len(combined_obs_df)} obs records, "
        f"{len(combined_forecast_df)} forecast records"
    )
    
    return combined_obs_df, combined_forecast_df


@task(timeout_seconds=60 * 10, retries=1)
def _load_to_warehouse_primary(
    ev: teehr.RemoteReadWriteEvaluation,
    obs_df: pd.DataFrame,
) -> None:
    """Load observations to warehouse primary_timeseries table."""
    logger = get_run_logger()
    
    if obs_df.empty:
        logger.warning("⚠️ No observations to load")
        return
    
    try:
        ev.primary_timeseries.append(obs_df)
        logger.info(f"✅ Loaded {len(obs_df)} observation records to warehouse")
    except Exception as e:
        logger.error(f"❌ Failed to load observations: {e}")
        raise


@task(timeout_seconds=60 * 10, retries=1)
def _load_to_warehouse_secondary(
    ev: teehr.RemoteReadWriteEvaluation,
    forecast_df: pd.DataFrame,
) -> None:
    """Load forecasts to warehouse secondary_timeseries table."""
    logger = get_run_logger()
    
    if forecast_df.empty:
        logger.warning("⚠️ No forecasts to load")
        return
    
    try:
        ev.secondary_timeseries.append(forecast_df)
        logger.info(f"✅ Loaded {len(forecast_df)} forecast records to warehouse")
    except Exception as e:
        logger.error(f"❌ Failed to load forecasts: {e}")
        raise


@flow(name="ingest-nrcs-streamflow-forecasts-observations-v2")
def ingest_nrcs_streamflow_forecasts_observations_v2(
    temp_dir_path: Union[str, Path] = "/data/temp-spark",
) -> None:
    """Main workflow for ingesting NRCS streamflow forecasts and observations.
    
    Per-location sequential processing:
    1. For each location: fetch obs and forecasts
    2. Identify unique full forecast periods
    3. Generate cumsum and final observed for those periods
    4. Process forecasts with Cases A/B/C reconstruction
    5. Combine all locations and load to warehouse
    """
    logger = get_run_logger()
    ev = None
    
    try:
        # Initialize
        ev = _initialize_evaluation(
            temp_dir_path=temp_dir_path,
            start_spark_cluster=False,
        )
        
        # Get location lists
        obs_location_ids = _get_nrcs_locations_observed(ev)
        forecast_location_ids = _get_nrcs_locations_forecast(ev)
        
        # Use intersection of both lists (must have both obs and forecasts)
        all_location_ids = sorted(set(obs_location_ids) & set(forecast_location_ids))
        
        if not all_location_ids:
            logger.warning("⚠️ No NRCS locations found with both observations and forecasts")
            return
        
        logger.info(f"Processing {len(all_location_ids)} NRCS locations")
        
        # Calculate date range (default: last 120 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()
        
        logger.info(f"Date range: {start_date_str} to {end_date_str}")
        
        # Process all locations sequentially
        obs_df, forecast_df = _process_all_locations(
            location_ids=all_location_ids,
            start_date=start_date_str,
            end_date=end_date_str,
        )
        
        if obs_df.empty or forecast_df.empty:
            logger.warning("⚠️ No data to load")
            return
        
        # Load to warehouse
        _load_to_warehouse_primary(ev, obs_df)
        _load_to_warehouse_secondary(ev, forecast_df)
        
        logger.info("✅ NRCS ingest v2 workflow completed successfully")
    
    except Exception as e:
        logger.error(f"❌ NRCS ingest v2 workflow failed: {e}")
        raise
    
    finally:
        if ev is not None:
            try:
                ev.spark.stop()
                logger.info("⏰ Spark session stopped")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping Spark: {e}")


__all__ = ["ingest_nrcs_streamflow_forecasts_observations_v2"]
