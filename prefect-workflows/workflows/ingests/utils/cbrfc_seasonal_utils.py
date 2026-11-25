"""Utilities for CBRFC seasonal water supply forecast/observation ingestion workflow.

This module provides functions to fetch, parse, and process CBRFC seasonal
water supply forecasts and observations for use in the Prefect workflow.

The module adapts functionality from the prototype warehouse utils to work
within the workflow context, with enhancements for water-year-based parameters
and updated variable naming conventions.
"""

import re
import warnings
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
import requests
from teehr.models.pandera_dataframe_schemas import (
    primary_timeseries_schema,
    secondary_timeseries_schema,
)


# CBRFC API Configuration
CBRFC_SEASONAL_WSUP_URL = "https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py"
SIM_CONFIGURATION_NAME = "cbrfc_unregulated_official_forecast"
OBS_CONFIGURATION_NAME = "cbrfc_unregulated_observed"
SEASONAL_WSUP_UNIT_NAME = "m^3"
KAF_TO_CUBIC_METERS = 1000 * 1233.48184
OBS_RAW_KEY = "Obs"

# Schema column management
sim_cols_raw = list(secondary_timeseries_schema(type="pandas").columns.keys())
obs_cols_raw = list(primary_timeseries_schema(type="pandas").columns.keys())
cols_to_remove = ["created_at", "updated_at"]
SIM_SCHEMA_COLUMNS = [x for x in sim_cols_raw if x not in cols_to_remove]
OBS_SCHEMA_COLUMNS = [x for x in obs_cols_raw if x not in cols_to_remove]

# Raw CBRFC field names to TEEHR variable names
RAW_KEYS_TO_TEEHR_VARIABLES = {
    "max": "max",
    "p10": "p10",
    "p30": "p30",
    "p50": "p50",
    "p70": "p70",
    "p90": "p90",
    "min": "min",
    "crx": "crx",
    "c30": "c30",
    "cmp": "cmp",
    "c70": "c70",
    "crn": "crn",
    "Obs": "Obs",
}

# Forecast period to variable name mapping
# Key: (start_month_name, end_month_name)
# Value: (variable_name, start_month_number)
SEASONAL_PERIODS = {
    ("april", "july"): ("volume_0407_sum", 4),
    ("january", "june"): ("volume_0106_sum", 1),
    ("january", "may"): ("volume_0105_sum", 1),
}

# Variable name to description mapping (forecast and observed cumsum)
CBRFC_SEASONAL_VARIABLE_MAPPING: dict[str, str] = {
    # Forecast variables
    "volume_0407_sum": "Seasonal summed water supply volume (Apr-Jul)",
    "volume_0106_sum": "Seasonal summed water supply volume (Jan-Jun)",
    "volume_0105_sum": "Seasonal summed water supply volume (Jan-May)",
    # Observed cumsum variables (new naming convention)
    "volume_0407_cumsum": "Seasonal summed water supply volume (Apr-Jul) (cumsum)",
    "volume_0106_cumsum": "Seasonal summed water supply volume (Jan-Jun) (cumsum)",
    "volume_0105_cumsum": "Seasonal summed water supply volume (Jan-May) (cumsum)",
}


# ============================================================================
# Water Year Utilities
# ============================================================================


def water_year_to_dates(water_year: int) -> Tuple[datetime, datetime]:
    """Convert a water year number to its start and end dates.

    Parameters
    ----------
    water_year : int
        The water year (e.g., 2025)

    Returns
    -------
    Tuple[datetime, datetime]
        Tuple of (start_date, end_date) where:
        - start_date = October 1st of (year - 1)
        - end_date = September 30th of year

    Examples
    --------
    >>> start, end = water_year_to_dates(2026)
    >>> start
    datetime.datetime(2025, 10, 1, 0, 0)
    >>> end
    datetime.datetime(2026, 9, 30, 23, 59, 59)
    """
    start = datetime(water_year - 1, 10, 1)
    end = datetime(water_year, 9, 30, 23, 59, 59)
    return start, end


def is_water_year_valid(water_year: int) -> bool:
    """Check if a water year is valid (reasonable range).

    Parameters
    ----------
    water_year : int
        The water year to validate

    Returns
    -------
    bool
        True if water year is in valid range (1950-2100)
    """
    return isinstance(water_year, int) and 1950 <= water_year <= 2100


def get_water_year_from_date(date: datetime) -> int:
    """Get the water year for a given date.

    Water year starts October 1st and ends September 30th.

    Parameters
    ----------
    date : datetime
        The date to get water year for

    Returns
    -------
    int
        The water year (e.g., 2025)

    Examples
    --------
    >>> get_water_year_from_date(datetime(2025, 10, 15))
    2026
    >>> get_water_year_from_date(datetime(2025, 9, 30))
    2025
    """
    if date.month >= 10:
        return date.year + 1
    return date.year


# ============================================================================
# CBRFC Data Fetching & Parsing
# ============================================================================


def _normalize_cbrfc_lid(site_id: str) -> str:
    """Normalize a location ID like 'cbrfc-OAWU1' to the CBRFC LID 'OAWU1'."""
    if not isinstance(site_id, str) or not site_id.strip():
        raise ValueError("site_id must be a non-empty string")
    return site_id.strip().removeprefix("cbrfc-").upper()


def _build_seasonal_wsup_url(site_id: str, year: int) -> str:
    """Build a CBRFC seasonal water supply forecast CSV URL."""
    lid = _normalize_cbrfc_lid(site_id)
    return f"{CBRFC_SEASONAL_WSUP_URL}?id={lid}&year={int(year)}&db=&csv=1"


def _is_parseable_number(value: str) -> bool:
    """Return True when a raw CSV field can be interpreted as a number."""
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _seasonal_variable_from_header(lines: list[str]) -> str:
    """Determine the aggregate variable from the CBRFC forecast headline."""
    forecast_header = next(
        (line for line in lines if "Runoff Forecast" in line),
        None,
    )
    if forecast_header is None:
        raise ValueError("Could not find CBRFC seasonal forecast headline")

    period_match = re.search(
        r"\b([A-Za-z]+)\s*-\s*([A-Za-z]+)\b",
        forecast_header,
    )
    if period_match is None:
        raise ValueError(
            f"Could not determine aggregation period from headline: {forecast_header}"
        )

    period = tuple(part.lower() for part in period_match.groups())
    try:
        variable_name, _ = SEASONAL_PERIODS[period]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported CBRFC seasonal aggregation period: "
            f"{period_match.group(0)}"
        ) from exc

    return variable_name


def _parse_seasonal_wsup_csv_text(
    csv_text: str,
) -> Tuple[pd.DataFrame, str]:
    """Parse CBRFC seasonal forecast CSV text and identify its aggregate variable.

    Parameters
    ----------
    csv_text : str
        Raw CSV text from CBRFC API response

    Returns
    -------
    Tuple[pd.DataFrame, str]
        Tuple of (forecast_dataframe, variable_name)
    """
    lines = [line.strip() for line in csv_text.splitlines()]
    variable_name = _seasonal_variable_from_header(lines)

    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("Run Date,")
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Could not find CBRFC seasonal forecast CSV header")

    columns = lines[header_index].split(",")
    records = []

    for line in lines[header_index + 1 :]:
        line = line.removesuffix("</pre>").strip()
        if not line:
            continue

        parts = [None if part in {"", "None"} else part for part in line.split(",")]
        if not parts or pd.isna(pd.to_datetime(parts[0], errors="coerce")):
            continue

        if len(parts) < len(columns):
            missing_count = len(columns) - len(parts)
            last_value = parts[-1]
            if last_value is not None and _is_parseable_number(last_value):
                parts = parts[:-1] + ([None] * missing_count) + [last_value]
            else:
                parts = parts + ([None] * missing_count)

        if len(parts) != len(columns):
            raise ValueError(
                f"Expected {len(columns)} columns but found {len(parts)} "
                f"in row: {line}"
            )

        records.append(parts)

    return pd.DataFrame(records, columns=columns), variable_name


def _split_seasonal_wsup_timeseries(
    forecast_df: pd.DataFrame,
    timestamp_column: str = "Run Date",
) -> dict[str, pd.DataFrame]:
    """Split a seasonal water supply forecast table into one DataFrame per series.

    Parameters
    ----------
    forecast_df : pd.DataFrame
        Raw forecast dataframe from CSV
    timestamp_column : str, default "Run Date"
        Name of the timestamp column

    Returns
    -------
    dict[str, pd.DataFrame]
        Dictionary mapping series names to their DataFrames
    """
    if timestamp_column not in forecast_df.columns:
        raise ValueError(
            f"Expected timestamp column '{timestamp_column}' in forecast data"
        )

    clean_df = forecast_df.copy()
    clean_df[timestamp_column] = pd.to_datetime(
        clean_df[timestamp_column],
        errors="coerce",
    )
    clean_df = clean_df.dropna(subset=[timestamp_column])

    timeseries = {}
    for column in clean_df.columns.drop(timestamp_column):
        series_df = clean_df[[timestamp_column, column]].copy()
        series_df[column] = (
            pd.to_numeric(series_df[column], errors="coerce")
            * KAF_TO_CUBIC_METERS
        ).round(3)
        timeseries[column] = series_df.dropna(subset=[column]).reset_index(
            drop=True
        )

    return timeseries


def _format_seasonal_wsup_timeseries(
    raw_key: str,
    timeseries_df: pd.DataFrame,
    location_id: str,
    configuration_name: str,
    variable_name: str,
    value_time: pd.Timestamp,
    timestamp_column: str = "Run Date",
    include_member: bool = False,
) -> pd.DataFrame:
    """Format one raw CBRFC seasonal series to the ingest schema.

    Parameters
    ----------
    raw_key : str
        Raw key from CBRFC data (e.g., 'max', 'p50', 'Obs')
    timeseries_df : pd.DataFrame
        Timeseries dataframe to format
    location_id : str
        Location ID for this data
    configuration_name : str
        Configuration name for this data
    variable_name : str
        Variable name for this data
    value_time : pd.Timestamp
        Value time for this data
    timestamp_column : str, default "Run Date"
        Name of the timestamp column
    include_member : bool, default False
        Whether to include member column (for forecast data)

    Returns
    -------
    pd.DataFrame
        Formatted dataframe matching schema
    """
    if raw_key not in RAW_KEYS_TO_TEEHR_VARIABLES:
        raise ValueError(f"Unknown CBRFC seasonal timeseries key '{raw_key}'")
    if timestamp_column not in timeseries_df.columns:
        raise ValueError(
            f"Expected timestamp column '{timestamp_column}' in {raw_key} timeseries"
        )
    if raw_key not in timeseries_df.columns:
        raise ValueError(f"Expected value column '{raw_key}' in {raw_key} timeseries")

    formatted = pd.DataFrame(
        {
            "reference_time": pd.to_datetime(timeseries_df[timestamp_column], utc=True),
            "value_time": pd.Series(
                pd.Timestamp(value_time, tz="UTC"),
                index=timeseries_df.index,
            ),
            "value": pd.to_numeric(
                timeseries_df[raw_key],
                errors="raise",
            ).astype(float),
            "variable_name": variable_name,
            "configuration_name": configuration_name,
            "unit_name": SEASONAL_WSUP_UNIT_NAME,
            "location_id": location_id,
        }
    )

    # Ensure timezone info is properly set (handle case where it might be lost)
    if formatted["reference_time"].dt.tz is None:
        formatted["reference_time"] = formatted["reference_time"].dt.tz_localize("UTC")
    if formatted["value_time"].dt.tz is None:
        formatted["value_time"] = formatted["value_time"].dt.tz_localize("UTC")

    if include_member:
        formatted["member"] = RAW_KEYS_TO_TEEHR_VARIABLES[raw_key]
        return formatted[SIM_SCHEMA_COLUMNS]

    # For observed (cumsum) data: set reference_time to NULL and move reference_time to value_time
    formatted["reference_time"] = pd.to_datetime([None] * len(formatted), utc=True)
    formatted["value_time"] = pd.to_datetime(timeseries_df[timestamp_column], utc=True)
    if formatted["value_time"].dt.tz is None:
        formatted["value_time"] = formatted["value_time"].dt.tz_localize("UTC")

    return formatted[OBS_SCHEMA_COLUMNS]


def _assemble_seasonal_wsup_site_data(
    timeseries: dict[str, pd.DataFrame],
    location_id: str,
    variable_name: str,
    value_time: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """Assemble simulated and observed ingest DataFrames for one location.

    Parameters
    ----------
    timeseries : dict[str, pd.DataFrame]
        Dictionary of timeseries by raw key
    location_id : str
        Location ID
    variable_name : str
        Variable name
    value_time : pd.Timestamp
        Value time for data

    Returns
    -------
    dict[str, pd.DataFrame]
        Dictionary with 'sim' and 'obs' dataframes
    """
    sim_frames = []
    obs_frames = []

    for raw_key, timeseries_df in timeseries.items():
        if raw_key == OBS_RAW_KEY:
            obs_frames.append(
                _format_seasonal_wsup_timeseries(
                    raw_key=raw_key,
                    timeseries_df=timeseries_df,
                    location_id=location_id,
                    configuration_name=OBS_CONFIGURATION_NAME,
                    variable_name=variable_name,
                    value_time=value_time,
                )
            )
        else:
            sim_frames.append(
                _format_seasonal_wsup_timeseries(
                    raw_key=raw_key,
                    timeseries_df=timeseries_df,
                    location_id=location_id,
                    configuration_name=SIM_CONFIGURATION_NAME,
                    variable_name=variable_name,
                    value_time=value_time,
                    include_member=True,
                )
            )

    sim_df = (
        pd.concat(sim_frames, ignore_index=True)
        if sim_frames
        else pd.DataFrame(columns=SIM_SCHEMA_COLUMNS)
    )
    obs_df = (
        pd.concat(obs_frames, ignore_index=True)
        if obs_frames
        else pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)
    )

    return {"sim": sim_df, "obs": obs_df}


def _fetch_seasonal_wsup_timeseries(
    site_id: str,
    year: int,
    timeout: int = 30,
) -> Tuple[dict[str, pd.DataFrame], str]:
    """Fetch a CBRFC seasonal forecast page into timeseries DataFrames.

    Parameters
    ----------
    site_id : str
        Location ID (e.g., 'cbrfc-OAWU1')
    year : int
        Water year to fetch
    timeout : int, default 30
        Request timeout in seconds

    Returns
    -------
    Tuple[dict[str, pd.DataFrame], str]
        Tuple of (timeseries_dict, variable_name)
    """
    url = _build_seasonal_wsup_url(site_id, year)

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Could not fetch CBRFC seasonal forecast from {url}: {exc}"
        ) from exc

    try:
        forecast_df, variable_name = _parse_seasonal_wsup_csv_text(response.text)
    except ValueError as exc:
        raise ValueError(
            f"Could not parse CBRFC seasonal forecast CSV from {url}: {exc}"
        ) from exc

    return _split_seasonal_wsup_timeseries(forecast_df), variable_name


def _fetch_seasonal_wsup_site_results(
    location_ids: list[str],
    year: int,
    timeout: int = 30,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Fetch and assemble seasonal water supply data for multiple locations.

    Parameters
    ----------
    location_ids : list[str]
        List of location IDs to fetch
    year : int
        Water year to fetch
    timeout : int, default 30
        Request timeout in seconds

    Returns
    -------
    dict[str, dict[str, pd.DataFrame]]
        Dictionary mapping location_id to {'sim': sim_df, 'obs': obs_df}
    """
    results = {}

    for location_id in location_ids:
        timeseries, variable_name = _fetch_seasonal_wsup_timeseries(
            location_id,
            year,
            timeout=timeout,
        )
        period = next(
            period
            for period, (mapped_variable, _) in SEASONAL_PERIODS.items()
            if mapped_variable == variable_name
        )
        _, start_month = SEASONAL_PERIODS[period]
        value_time = pd.Timestamp(year=int(year), month=start_month, day=1)

        results[location_id] = _assemble_seasonal_wsup_site_data(
            timeseries,
            location_id,
            variable_name,
            value_time,
        )

    return results


# ============================================================================
# Variable Renaming & Final Observed Timeseries
# ============================================================================


def rename_observed_variables(obs_df: pd.DataFrame) -> pd.DataFrame:
    """Rename observed variables from _sum to _cumsum naming convention.

    Renames volume_XXXX_sum to volume_XXXX_cumsum to indicate that
    the observed data represents cumulative sums over the forecast period.

    Parameters
    ----------
    obs_df : pd.DataFrame
        Observation dataframe with variable_name column

    Returns
    -------
    pd.DataFrame
        Dataframe with renamed variables
    """
    if obs_df.empty:
        return obs_df

    renamed_df = obs_df.copy()

    # Create mapping from _sum to _cumsum
    for period_key, (sum_var_name, _) in SEASONAL_PERIODS.items():
        cumsum_var_name = sum_var_name.replace("_sum", "_cumsum")
        renamed_df.loc[
            renamed_df["variable_name"] == sum_var_name, "variable_name"
        ] = cumsum_var_name

    return renamed_df


def create_final_observed_timeseries(
    obs_df: pd.DataFrame,
    forecast_period_start_date: datetime,
    variable_name: str,
    location_id: str,
    sim_df: pd.DataFrame = None,
    check_period_ended: bool = True,
) -> pd.DataFrame:
    """Create a final observed timeseries from the last cumsum value.

    This creates a single-row dataframe with the last reported cumsum value
    from the observed timeseries. This is used for metric calculations where
    we need a single point-in-time observation value to compare against
    forecast data.

    Parameters
    ----------
    obs_df : pd.DataFrame
        Observation dataframe (should already have cumsum variable names)
    forecast_period_start_date : datetime
        Start date of the forecast period (used as value_time)
    variable_name : str
        Variable name (should be _sum format, e.g., 'volume_0407_sum')
    location_id : str
        Location ID
    sim_df : pd.DataFrame, optional
        Simulation/forecast dataframe to extract reference_time from.
        If provided, uses the reference_time from the first matching forecast row.
    check_period_ended : bool, default True
        If True, only create if forecast period has ended

    Returns
    -------
    pd.DataFrame
        Single-row dataframe with final observed value, or empty dataframe

    Raises
    ------
    ValueError
        If obs_df is empty or other validation fails
    """
    if obs_df.empty:
        return pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)

    # Check if forecast period has ended
    if check_period_ended:
        forecast_end_month = forecast_period_start_date.month + 3  # April -> July
        forecast_end_day = 30
        if forecast_end_month > 12:
            forecast_end_month -= 12
            forecast_end_year = forecast_period_start_date.year + 1
        else:
            forecast_end_year = forecast_period_start_date.year

        forecast_end = datetime(forecast_end_year, forecast_end_month, forecast_end_day)
        if datetime.now() < forecast_end:
            # Forecast period hasn't ended yet
            return pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)

    # Get the last value from observation data
    last_row = obs_df.iloc[-1].copy()
    last_value = last_row["value"]
    
    # reference_time should be the last day of the forecast period
    # For April-July (0407), that's July 31st
    forecast_end_month = forecast_period_start_date.month + 3  # April -> July
    forecast_end_day = 30
    if forecast_end_month > 12:
        forecast_end_month -= 12
        forecast_end_year = forecast_period_start_date.year + 1
    else:
        forecast_end_year = forecast_period_start_date.year
    
    reference_time_value = pd.Timestamp(
        year=forecast_end_year,
        month=forecast_end_month,
        day=forecast_end_day,
        tz="UTC"
    )
    
    # value_time should match the forecast data value_time (which is typically forecast_period_start_date)
    value_time_value = pd.Timestamp(forecast_period_start_date, tz="UTC")

    # Create final observed row with forecast variable name (not cumsum)
    final_obs_df = pd.DataFrame(
        [
            {
                "reference_time": reference_time_value,
                "value_time": value_time_value,
                "value": last_value,
                "variable_name": variable_name,  # Use _sum format
                "configuration_name": OBS_CONFIGURATION_NAME,
                "unit_name": SEASONAL_WSUP_UNIT_NAME,
                "location_id": location_id,
            }
        ]
    )

    return final_obs_df[OBS_SCHEMA_COLUMNS]


def _filter_unmapped_variables(
    df: pd.DataFrame,
    *,
    variable_mapping: dict[str, str],
) -> pd.DataFrame:
    """Filter dataframe to only include variables in the mapping and warn about filtered data.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a 'variable_name' column
    variable_mapping : dict[str, str]
        Mapping of valid variable names to their descriptions

    Returns
    -------
    pd.DataFrame
        DataFrame with only variables present in variable_mapping
    """
    if df.empty:
        return df

    unmapped_vars = set(df["variable_name"].unique()) - set(variable_mapping.keys())
    if unmapped_vars:
        warnings.warn(
            f"The following variables were not found in CBRFC_SEASONAL_VARIABLE_MAPPING "
            f"and will be filtered out: {sorted(unmapped_vars)}",
            UserWarning,
            stacklevel=3,
        )
        df = df[df["variable_name"].isin(variable_mapping.keys())].reset_index(
            drop=True
        )

    return df


def _combine_seasonal_wsup_results(
    seasonal_results: dict[str, dict[str, pd.DataFrame]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Combine site-keyed results into simulated and observed DataFrames.

    Parameters
    ----------
    seasonal_results : dict[str, dict[str, pd.DataFrame]]
        Dictionary mapping location_id to {'sim': sim_df, 'obs': obs_df}

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        Tuple of (sim_df, obs_df) combined across all locations
    """
    sim_frames = []
    obs_frames = []

    for location_id, site_results in seasonal_results.items():
        if "sim" not in site_results or "obs" not in site_results:
            raise ValueError(
                f"Expected 'sim' and 'obs' results for location '{location_id}'"
            )

        sim_frames.append(site_results["sim"])
        obs_frames.append(site_results["obs"])

    sim_df = (
        pd.concat(sim_frames, ignore_index=True)
        if sim_frames
        else pd.DataFrame(columns=SIM_SCHEMA_COLUMNS)
    )
    obs_df = (
        pd.concat(obs_frames, ignore_index=True)
        if obs_frames
        else pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)
    )

    sim_df = sim_df[SIM_SCHEMA_COLUMNS]
    obs_df = obs_df[OBS_SCHEMA_COLUMNS]

    # Filter to only include mapped variables
    sim_df = _filter_unmapped_variables(
        sim_df, variable_mapping=CBRFC_SEASONAL_VARIABLE_MAPPING
    )
    obs_df = _filter_unmapped_variables(
        obs_df, variable_mapping=CBRFC_SEASONAL_VARIABLE_MAPPING
    )

    return sim_df, obs_df


# ============================================================================
# Public API Functions
# ============================================================================


def fetch_seasonal_wsup_forecasts(
    location_ids: list[str],
    year: int,
    timeout: int = 30,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch CBRFC seasonal forecasts as simulated and observed DataFrames.

    Data is filtered to only include variables defined in CBRFC_SEASONAL_VARIABLE_MAPPING.
    A warning is issued for any variables that are filtered out.

    Parameters
    ----------
    location_ids : list[str]
        List of location IDs to fetch (e.g., ['cbrfc-OAWU1', 'cbrfc-GRNU1'])
    year : int
        Water year to fetch
    timeout : int, default 30
        Request timeout in seconds

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        Tuple of (sim_df, obs_df) with forecast and observation data
    """
    seasonal_results = _fetch_seasonal_wsup_site_results(
        location_ids,
        year,
        timeout=timeout,
    )
    return _combine_seasonal_wsup_results(seasonal_results)


__all__ = [
    "fetch_seasonal_wsup_forecasts",
    "CBRFC_SEASONAL_VARIABLE_MAPPING",
    "SEASONAL_PERIODS",
    "water_year_to_dates",
    "is_water_year_valid",
    "get_water_year_from_date",
    "rename_observed_variables",
    "create_final_observed_timeseries",
]
