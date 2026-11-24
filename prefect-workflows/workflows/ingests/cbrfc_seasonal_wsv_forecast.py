"""CBRFC seasonal water supply forecast/observation ingestion workflow.

This workflow fetches CBRFC seasonal water supply forecasts and observations
for specified water years and locations, then writes the data to the warehouse.

The workflow uses water-year-based parameters (instead of calendar dates) and
updates variable naming conventions for observed data to include cumulative
sum information.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from prefect import flow, get_run_logger, task
from teehr import Configuration

from workflows.ingests.utils.cbrfc_seasonal_utils import (
    CBRFC_SEASONAL_VARIABLE_MAPPING,
    OBS_CONFIGURATION_NAME,
    SIM_CONFIGURATION_NAME,
    create_final_observed_timeseries,
    fetch_seasonal_wsup_forecasts,
    get_water_year_from_date,
    is_water_year_valid,
    rename_observed_variables,
    water_year_to_dates,
)
from workflows.utils.common_utils import initialize_evaluation, load_to_warehouse

logging.getLogger("teehr").setLevel(logging.INFO)


def _get_all_cbrfc_locations(ev) -> list[str]:
    """Get list of all CBRFC locations from warehouse.

    Parameters
    ----------
    ev
        TEEHR Evaluation object

    Returns
    -------
    list[str]
        List of CBRFC location IDs (e.g., ['cbrfc-OAWU1', 'cbrfc-GRNU1', ...])
    """
    sdf = ev.location_id_aliases.filter("location_id_alias LIKE 'cbrfc-%'").to_sdf()
    locs = [row["location_id_alias"] for row in sdf.select("location_id_alias").collect()]

    return locs


@task(name="fetch-cbrfc-data")
def _fetch_cbrfc_data_for_water_year(
    location_ids: list[str],
    water_year: int,
    timeout: int = 30,
) -> dict:
    """Fetch CBRFC data for a single water year and all locations.

    Parameters
    ----------
    location_ids : list[str]
        List of location IDs to fetch
    water_year : int
        Water year to fetch
    timeout : int, default 30
        Request timeout in seconds

    Returns
    -------
    dict
        Dictionary with 'sim_df' and 'obs_df' keys containing merged data
    """
    logger = get_run_logger()
    logger.info(f"Fetching CBRFC data for WY {water_year} ({len(location_ids)} locations)")

    try:
        sim_df, obs_df = fetch_seasonal_wsup_forecasts(
            location_ids=location_ids,
            year=water_year,
            timeout=timeout,
        )
        logger.info(
            f"✅ Fetched {len(sim_df)} forecast rows and {len(obs_df)} observation rows"
        )
        return {"sim_df": sim_df, "obs_df": obs_df}
    except Exception as e:
        logger.error(f"✗ Error fetching CBRFC data for WY {water_year}: {e}")
        raise


@task(name="process-cbrfc-data")
def _process_cbrfc_data(
    fetch_result: dict,
    water_year: int,
    forecast_period_start_date: datetime,
) -> dict:
    """Process fetched CBRFC data: rename variables, create final obs, etc.

    Parameters
    ----------
    fetch_result : dict
        Result from fetch task with 'sim_df' and 'obs_df'
    water_year : int
        Water year for reference
    forecast_period_start_date : datetime
        Start date of the forecast period (April 1 for April-July)

    Returns
    -------
    dict
        Dictionary with 'sim_df', 'obs_df', and 'final_obs_df'
    """
    logger = get_run_logger()
    logger.info(f"Processing CBRFC data for WY {water_year}")

    sim_df = fetch_result["sim_df"]
    obs_df = fetch_result["obs_df"]

    # Rename observed variables to cumsum naming convention
    obs_df = rename_observed_variables(obs_df)
    logger.info(
        f"Renamed observed variables to cumsum naming: "
        f"{obs_df['variable_name'].unique()}"
    )

    # Create final observed timeseries (last cumsum value)
    final_obs_frames = []
    for location_id in obs_df["location_id"].unique():
        location_obs = obs_df[obs_df["location_id"] == location_id].copy()
        if not location_obs.empty:
            # Determine the original variable name (without cumsum)
            # by checking which forecast variable this location has
            sim_vars = sim_df[sim_df["location_id"] == location_id][
                "variable_name"
            ].unique()
            if len(sim_vars) > 0:
                variable_name = sim_vars[0]  # Use forecast variable name
                final_obs = create_final_observed_timeseries(
                    location_obs,
                    forecast_period_start_date=forecast_period_start_date,
                    variable_name=variable_name,
                    location_id=location_id,
                    check_period_ended=True,
                )
                if not final_obs.empty:
                    final_obs_frames.append(final_obs)

    final_obs_df = (
        pd.concat(final_obs_frames, ignore_index=True)
        if final_obs_frames
        else pd.DataFrame()
    )

    logger.info(f"Created {len(final_obs_df)} final observed timeseries rows")

    return {"sim_df": sim_df, "obs_df": obs_df, "final_obs_df": final_obs_df}


@task(name="write-to-warehouse")
def _write_to_warehouse(
    ev,
    sim_df: pd.DataFrame,
    obs_df: pd.DataFrame,
    final_obs_df: pd.DataFrame,
    temp_dir_path: Union[str, Path],
) -> None:
    """Write simulation, observation, and final observed data to warehouse.

    Parameters
    ----------
    ev
        TEEHR Evaluation object
    sim_df : pd.DataFrame
        Simulation/forecast data
    obs_df : pd.DataFrame
        Observation data (cumsum)
    final_obs_df : pd.DataFrame
        Final observed (single-value) timeseries
    temp_dir_path : Union[str, Path]
        Path to temporary directory for parquet files
    """
    logger = get_run_logger()

    temp_dir_path = Path(temp_dir_path)
    temp_dir_path.mkdir(parents=True, exist_ok=True)

    # Write forecast data to secondary_timeseries
    if not sim_df.empty:
        sim_parquet_path = temp_dir_path / "cbrfc_forecast"
        sim_parquet_path.mkdir(parents=True, exist_ok=True)
        sim_df.to_parquet(sim_parquet_path / "data.parquet")
        logger.info(f"Writing {len(sim_df)} forecast rows to warehouse")
        load_to_warehouse(
            ev=ev,
            in_path=sim_parquet_path,
            table_name="secondary_timeseries",
            write_mode="upsert",
            drop_duplicates=False,
        )
        logger.info("✅ Forecast data written to warehouse")
    else:
        logger.warning("No forecast data to write")

    # Write observation data to primary_timeseries
    if not obs_df.empty:
        obs_parquet_path = temp_dir_path / "cbrfc_obs_cumsum"
        obs_parquet_path.mkdir(parents=True, exist_ok=True)
        obs_df.to_parquet(obs_parquet_path / "data.parquet")
        logger.info(f"Writing {len(obs_df)} observation (cumsum) rows to warehouse")
        load_to_warehouse(
            ev=ev,
            in_path=obs_parquet_path,
            table_name="primary_timeseries",
            write_mode="upsert",
            drop_duplicates=False,
        )
        logger.info("✅ Observation (cumsum) data written to warehouse")
    else:
        logger.warning("No observation data to write")

    # Write final observed data to primary_timeseries
    if not final_obs_df.empty:
        final_obs_parquet_path = temp_dir_path / "cbrfc_obs_final"
        final_obs_parquet_path.mkdir(parents=True, exist_ok=True)
        final_obs_df.to_parquet(final_obs_parquet_path / "data.parquet")
        logger.info(f"Writing {len(final_obs_df)} final observed rows to warehouse")
        load_to_warehouse(
            ev=ev,
            in_path=final_obs_parquet_path,
            table_name="primary_timeseries",
            write_mode="upsert",
            drop_duplicates=False,
        )
        logger.info("✅ Final observed data written to warehouse")
    else:
        logger.info("No final observed data to write (forecast period may not have ended)")


@flow(
    name="ingest-cbrfc-seasonal-wsv-forecasts",
    flow_run_name="ingest-cbrfc-seasonal-wsv-forecasts-{water_year}",
    timeout_seconds=60 * 60,
)
def ingest_cbrfc_seasonal_wsv_forecasts(
    temp_dir_path: Union[str, Path],
    end_WY: int,
    start_WY: Optional[int] = None,
    location_ids: Optional[list[str]] = None,
    start_spark_cluster: bool = False,
) -> None:
    """Ingest CBRFC seasonal water supply forecasts and observations.

    This workflow fetches CBRFC seasonal forecasts and observations for one
    or more water years, processes them according to the TEEHR schema, and
    writes them to the warehouse.

    Parameters
    ----------
    temp_dir_path : Union[str, Path]
        Path to temporary directory for intermediate data
    end_WY : int
        Ending water year (required)
    start_WY : Optional[int], default None
        Starting water year. If None, only end_WY is used. If provided,
        the workflow processes all years from start_WY to end_WY inclusive.
    location_ids : Optional[list[str]], default None
        List of specific location IDs to fetch. If None, all CBRFC locations
        are fetched.
    start_spark_cluster : bool, default False
        Whether to start a Spark cluster for processing

    Raises
    ------
    ValueError
        If water year parameters are invalid
    """
    logger = get_run_logger()

    logger.info("=" * 80)
    logger.info("CBRFC Seasonal Water Supply Forecast Ingestion")
    logger.info("=" * 80)

    # Validate parameters
    if not is_water_year_valid(end_WY):
        raise ValueError(f"Invalid end_WY: {end_WY}")

    if start_WY is None:
        start_WY = end_WY
    elif not is_water_year_valid(start_WY):
        raise ValueError(f"Invalid start_WY: {start_WY}")

    if start_WY > end_WY:
        raise ValueError(f"start_WY ({start_WY}) cannot be greater than end_WY ({end_WY})")

    logger.info(f"Processing water years: {start_WY} to {end_WY}")

    # Initialize warehouse
    ev = initialize_evaluation(
        temp_dir_path=temp_dir_path,
        start_spark_cluster=start_spark_cluster,
        update_configs={"spark.sql.shuffle.partitions": "4"},
    )

    # Get location IDs
    if location_ids is None:
        location_ids = _get_all_cbrfc_locations(ev)
    logger.info(f"Processing {len(location_ids)} locations")

    # Process each water year
    all_sim_dfs = []
    all_obs_dfs = []
    all_final_obs_dfs = []

    for water_year in range(start_WY, end_WY + 1):
        logger.info(f"\n--- Processing Water Year {water_year} ---")

        # Fetch data
        fetch_result = _fetch_cbrfc_data_for_water_year(
            location_ids=location_ids,
            water_year=water_year,
            timeout=30,
        )

        # Determine forecast period start date (April 1 for April-July)
        forecast_period_start_date = datetime(water_year, 4, 1)

        # Process data
        process_result = _process_cbrfc_data(
            fetch_result=fetch_result,
            water_year=water_year,
            forecast_period_start_date=forecast_period_start_date,
        )

        # Collect results
        if not process_result["sim_df"].empty:
            all_sim_dfs.append(process_result["sim_df"])
        if not process_result["obs_df"].empty:
            all_obs_dfs.append(process_result["obs_df"])
        if not process_result["final_obs_df"].empty:
            all_final_obs_dfs.append(process_result["final_obs_df"])

        logger.info(f"✅ Completed processing WY {water_year}")

    # Combine all results
    combined_sim_df = (
        pd.concat(all_sim_dfs, ignore_index=True)
        if all_sim_dfs
        else pd.DataFrame()
    )
    combined_obs_df = (
        pd.concat(all_obs_dfs, ignore_index=True)
        if all_obs_dfs
        else pd.DataFrame()
    )
    combined_final_obs_df = (
        pd.concat(all_final_obs_dfs, ignore_index=True)
        if all_final_obs_dfs
        else pd.DataFrame()
    )

    logger.info(
        f"\nFinal data volumes:"
        f"\n  Forecast: {len(combined_sim_df)} rows"
        f"\n  Observation (cumsum): {len(combined_obs_df)} rows"
        f"\n  Final observed: {len(combined_final_obs_df)} rows"
    )

    # Write to warehouse
    _write_to_warehouse(
        ev=ev,
        sim_df=combined_sim_df,
        obs_df=combined_obs_df,
        final_obs_df=combined_final_obs_df,
        temp_dir_path=temp_dir_path,
    )

    # Cleanup
    if start_spark_cluster:
        ev.spark.stop()

    logger.info("\n" + "=" * 80)
    logger.info("✅ CBRFC Seasonal Water Supply Forecast Ingestion Complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    # For testing
    ingest_cbrfc_seasonal_wsv_forecasts(
        temp_dir_path="/data/temp-spark",
        end_WY=2025,
    )
