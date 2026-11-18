"""Ingest NRCS AWDB streamflow forecasts and observations.

This workflow fetches both NRCS-adjusted forecast and observed SRVO (Snow Water
Equivalent) data from the NRCS AWDB REST API and loads it into the teehr warehouse.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Union

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
def _build_forecast_period_metadata_from_dataframe(
    forecast_df: pd.DataFrame,
) -> dict[int, dict[str, Any]]:
    """Build forecast period metadata directly from forecast DataFrame.
    
    Since we only have the flattened forecast DataFrame (not the original API response),
    we infer the forecast periods by analyzing variable_name patterns.
    
    Key logic: NRCS forecasts are truncated as months progress (Apr-Jul → May-Jul → Jun-Jul).
    All these truncated variants (0407, 0507, 0607) belong to the SAME forecast period.
    For each end_month found in the data, we identify the earliest start_month,
    considering only the periods present in the data (not merged across locations).
    
    Example:
        Input variables: volume_0407, volume_0507, volume_0607, volume_0409, volume_0509
        Grouped by end_month:
          - end_month=7: [0407, 0507, 0607] → earliest start_month=4 → volume_0407
          - end_month=9: [0409, 0509] → earliest start_month=4 → volume_0409
        Output metadata:
          {7: {start_month: 4, end_month: 7, variable_base: 'volume_0407'},
           9: {start_month: 4, end_month: 9, variable_base: 'volume_0409'}}
    
    Args:
        forecast_df: DataFrame with forecast data including variable_name column.
    
    Returns:
        Dict mapping end_month (int) to metadata with keys:
        start_month, end_month, variable_base, etc.
    """
    if forecast_df.empty:
        return {}
    
    # Collect all (start_month, end_month) pairs from ALL variables in the data
    periods_by_end_month: dict[int, list[int]] = {}
    
    for var_name in forecast_df["variable_name"].unique():
        if not isinstance(var_name, str) or "_" not in var_name:
            continue
        
        parts = var_name.split("_")
        if len(parts) < 2:
            continue
        
        mmdd = parts[1] if len(parts) > 1 else None
        if not mmdd or len(mmdd) < 4:
            continue
        
        try:
            start_month = int(mmdd[0:2])
            end_month = int(mmdd[2:4])
        except (ValueError, IndexError):
            continue
        
        # Basic validation of months
        if start_month < 1 or start_month > 12 or end_month < 1 or end_month > 12:
            continue
        
        # Collect all start_months for each end_month
        if end_month not in periods_by_end_month:
            periods_by_end_month[end_month] = []
        periods_by_end_month[end_month].append(start_month)
    
    # For each end_month, the earliest start_month represents the full period
    metadata = {}
    for end_month, start_months in periods_by_end_month.items():
        earliest_start = min(start_months)
        metadata[end_month] = {
            "start_month": earliest_start,
            "end_month": end_month,
            "variable_base": f"volume_{earliest_start:02d}{end_month:02d}",
        }
    
    return metadata


@task(cache_policy=NO_CACHE)
@task(cache_policy=NO_CACHE)
def _process_observed_cumsum(
    obs_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
    forecast_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Generate cumulative sum observations from monthly observations."""
    logger = get_run_logger()

    if obs_df.empty or not forecast_period_metadata:
        logger.info("⚠️ Skipping cumsum generation (empty data or metadata)")
        return pd.DataFrame()

    try:
        cumsum_df = nrcs_utils._generate_observed_cumsum(obs_df, forecast_period_metadata, forecast_df)
        logger.info(f"✅ Generated {len(cumsum_df)} cumsum observation records")
        return cumsum_df
    except Exception as e:
        logger.warning(f"⚠️ Failed to generate cumsum observations: {e}")
        return pd.DataFrame()


@task(cache_policy=NO_CACHE)
def _process_forecast_reconstruction(
    forecast_df: pd.DataFrame,
    cumsum_obs_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Reconstruct full-period forecasts from truncated API data."""
    logger = get_run_logger()

    if forecast_df.empty or not forecast_period_metadata:
        logger.info("⚠️ Skipping forecast reconstruction (empty data or metadata)")
        return forecast_df

    try:
        reconstructed_df = nrcs_utils._reconstruct_full_period_forecasts(
            forecast_df, cumsum_obs_df, forecast_period_metadata
        )
        logger.info(f"✅ Reconstructed {len(reconstructed_df)} forecast records")
        return reconstructed_df
    except Exception as e:
        logger.warning(f"⚠️ Failed to reconstruct forecasts: {e}")
        return forecast_df


@task(cache_policy=NO_CACHE)
def _process_final_observed_values(
    cumsum_obs_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Generate final observed values from cumsum observations."""
    logger = get_run_logger()

    if cumsum_obs_df.empty or not forecast_period_metadata:
        logger.info("⚠️ Skipping final observed generation (empty cumsum data or metadata)")
        return pd.DataFrame()

    try:
        final_obs_df = nrcs_utils._generate_final_observed_value(
            cumsum_obs_df, forecast_period_metadata
        )
        logger.info(f"✅ Generated {len(final_obs_df)} final observed records")
        return final_obs_df
    except Exception as e:
        logger.warning(f"⚠️ Failed to generate final observed values: {e}")
        return pd.DataFrame()


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

        # Process forecasts to extract period metadata and generate adjusted timeseries
        logger.info("Processing NRCS forecast periods and observations...")
        
        # Extract forecast period metadata from variable names in forecast DataFrame
        forecast_period_metadata = _build_forecast_period_metadata_from_dataframe(forecast_df)
        
        if not forecast_period_metadata:
            logger.warning("⚠️ No forecast periods identified in data")
        else:
            # Generate cumulative sum observations
            cumsum_obs_df = _process_observed_cumsum(obs_df, forecast_period_metadata, forecast_df)
            if not cumsum_obs_df.empty:
                obs_df = pd.concat([obs_df, cumsum_obs_df], ignore_index=True)
                logger.info(f"Added {len(cumsum_obs_df)} cumsum observations to dataset")
            
            # Reconstruct full-period forecasts from truncated API data
            reconstructed_forecast_df = _process_forecast_reconstruction(
                forecast_df, cumsum_obs_df, forecast_period_metadata
            )
            if not reconstructed_forecast_df.empty:
                forecast_df = pd.concat(
                    [forecast_df, reconstructed_forecast_df], ignore_index=True
                )
                logger.info(
                    f"Added {len(reconstructed_forecast_df)} reconstructed forecasts to dataset"
                )
            
            # Generate final observed values at end of periods
            final_obs_df = _process_final_observed_values(
                cumsum_obs_df, forecast_period_metadata
            )
            if not final_obs_df.empty:
                obs_df = pd.concat([obs_df, final_obs_df], ignore_index=True)
                logger.info(f"Added {len(final_obs_df)} final observed values to dataset")

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
