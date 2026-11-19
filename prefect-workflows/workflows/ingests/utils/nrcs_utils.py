"""Fetching and formatting utilities for NRCS AWDB data in Prefect workflows.

Includes client accessor and response wrappers for the NRCS AWDB REST API.
API docs: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html#/
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from teehr.models.pandera_dataframe_schemas import primary_timeseries_schema
from teehr.models.pandera_dataframe_schemas import secondary_timeseries_schema

# =============================================================================
# NRCS AWDB REST API Client
# =============================================================================

BASE_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
DEFAULT_TIMEOUT = 60


class _DataResponse(list):
    """List of observed data payloads with attached query parameters.

    Subclasses `list` so standard list operations, iteration, indexing,
    and `json.dumps()` continue to work natively.
    """

    def __init__(
        self,
        iterable: Sequence[dict[str, Any]] = (),
        *,
        begin_date: str | None = None,
        end_date: str | None = None,
        duration: str = "DAILY",
        query_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(iterable)
        self.begin_date = begin_date
        self.end_date = end_date
        self.duration = duration
        self.query_params = query_params or {}


class _ForecastResponse(list):
    """List of station forecast payloads with attached query metadata.

    Subclasses `list` so standard list operations, iteration, indexing,
    and `json.dumps()` continue to work natively.
    """

    def __init__(
        self,
        iterable: Sequence[dict[str, Any]] = (),
        *,
        begin_publication_date: str | None = None,
        end_publication_date: str | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(iterable)
        self.begin_publication_date = begin_publication_date
        self.end_publication_date = end_publication_date
        self.query_params = query_params or {}


def _normalize_station_triplet(station_triplet: str) -> str:
    """Normalize station IDs, allowing inputs like 'nrcs-09361500:CO:USGS'."""
    cleaned = station_triplet.strip()
    if cleaned.lower().startswith("nrcs-"):
        cleaned = cleaned[5:]
    return cleaned


def _to_csv(
    value: str | Sequence[str] | None,
    *,
    normalize_station_triplets: bool = False,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        result = value.strip()
        if normalize_station_triplets and result:
            return _normalize_station_triplet(result)
        return result or None

    items = [str(item).strip() for item in value if str(item).strip()]
    if normalize_station_triplets:
        items = [_normalize_station_triplet(item) for item in items]
    return ",".join(items) if items else None


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None and value != ""}


def _get(endpoint: str, params: dict[str, Any], *, timeout: int = DEFAULT_TIMEOUT) -> Any:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    response = requests.get(
        url,
        params=_clean_params(params),
        headers={"accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _water_year(dt: Any) -> int:
    """Return the water year (October 1 to September 30) for a given date."""
    ts = pd.to_datetime(dt, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Invalid date: {dt!r}; cannot determine water year.")
    return ts.year + 1 if ts.month >= 10 else ts.year


def _water_year_bounds(
    begin_date: str | datetime | pd.Timestamp | None,
    end_date: str | datetime | pd.Timestamp | None,
) -> tuple[str | None, str | None]:
    """Return YYYY-MM-DD bounds for the full water year(s) covering begin_date and end_date."""
    expanded_begin = None
    expanded_end = None

    if begin_date is not None:
        ts_begin = pd.to_datetime(begin_date, errors="coerce")
        if pd.isna(ts_begin):
            raise ValueError(f"Invalid begin_publication_date: {begin_date!r}")
        start_wy = _water_year(ts_begin)
        expanded_begin = f"{start_wy - 1}-10-01"

    if end_date is not None:
        ts_end = pd.to_datetime(end_date, errors="coerce")
        if pd.isna(ts_end):
            raise ValueError(f"Invalid end_publication_date: {end_date!r}")
        end_wy = _water_year(ts_end)
        expanded_end = f"{end_wy}-09-30"

    return expanded_begin, expanded_end


def _get_data(
    station_triplets: str | Sequence[str],
    elements: str | Sequence[str],
    *,
    duration: str = "DAILY",
    begin_date: str | None = None,
    end_date: str | None = None,
    insert_or_update_begin_date: str | None = None,
    period_ref: str = "END",
    central_tendency_type: str = "NONE",
    return_flags: bool = False,
    return_original_values: bool = False,
    return_suspect_data: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    **extra_params: Any,
) -> _DataResponse:
    """Get observed data from `/services/v1/data`."""
    params = {
        "stationTriplets": _to_csv(station_triplets, normalize_station_triplets=True),
        "elements": _to_csv(elements),
        "duration": duration,
        "beginDate": begin_date,
        "endDate": end_date,
        "insertOrUpdateBeginDate": insert_or_update_begin_date,
        "periodRef": period_ref,
        "centralTendencyType": central_tendency_type,
        "returnFlags": return_flags,
        "returnOriginalValues": return_original_values,
        "returnSuspectData": return_suspect_data,
    }
    params.update(extra_params)
    raw_response = _get("data", params, timeout=timeout)
    return _DataResponse(
        raw_response or [],
        begin_date=begin_date,
        end_date=end_date,
        duration=duration,
        query_params=_clean_params(params),
    )


def _get_forecasts(
    station_triplets: str | Sequence[str],
    *,
    element_codes: str | Sequence[str] | None = None,
    begin_publication_date: str | None = None,
    end_publication_date: str | None = None,
    exceedence_probabilities: str | Sequence[str | int] | None = None,
    forecast_periods: str | Sequence[str] | None = None,
    expand_water_years: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    **extra_params: Any,
) -> _ForecastResponse:
    """Get forecast data from `/services/v1/forecasts`.

    When `expand_water_years` is True (default), queries the full water year(s)
    spanned by `begin_publication_date` and `end_publication_date` behind the
    scenes to guarantee baseline periods and value_time can be derived.
    """
    api_begin_date = begin_publication_date
    api_end_date = end_publication_date

    if expand_water_years:
        expanded_begin, expanded_end = _water_year_bounds(
            begin_publication_date,
            end_publication_date,
        )
        if expanded_begin is not None:
            api_begin_date = expanded_begin
        if expanded_end is not None:
            api_end_date = expanded_end

    params = {
        "stationTriplets": _to_csv(station_triplets, normalize_station_triplets=True),
        "elementCodes": _to_csv(element_codes),
        "beginPublicationDate": api_begin_date,
        "endPublicationDate": api_end_date,
        "exceedenceProbabilities": _to_csv(exceedence_probabilities),
        "forecastPeriods": _to_csv(forecast_periods),
    }
    params.update(extra_params)
    raw_response = _get("forecasts", params, timeout=timeout)

    return _ForecastResponse(
        raw_response or [],
        begin_publication_date=begin_publication_date,
        end_publication_date=end_publication_date,
        query_params=_clean_params(params),
    )


# =============================================================================
# NRCS Data Formatting and Utilities
# =============================================================================

AC_FT_TO_M3 = 1_233.48183754752
KAC_FT_TO_M3 = 1_233_481.83754752

MONTH_INITIALS = ("j", "f", "m", "a", "m", "j", "j", "a", "s", "o", "n", "d")

UNIT_CODE_TO_CONVERSION_MAPPING: dict[str, float] = {
    "kac_ft": KAC_FT_TO_M3,
    "ac_ft": AC_FT_TO_M3,
}

CONFIG_TO_ELEMENT_MAPPING: dict[str, list[str]] = {
    "nrcs_adjusted_forecast": ["SRVO"],
    "nrcs_adjusted_observed": ["SRVO"],
}

ELEMENT_TO_VARIABLE_MAPPING: dict[str, dict[str, Any]] = {
    "SRVO": {
        "parameter": "volume",
        "statistic": "sum",
        "conversion": [KAC_FT_TO_M3, AC_FT_TO_M3],
        "target_unit": "m^3",
    },
}

NRCS_VARIABLE_MAPPING: dict[str, str] = {
    # Full forecast periods (earliest start for each end month)
    # Only these represent the complete forecast period for analysis
    "volume_0207_sum": "Seasonal summed water supply volume (Feb-Jul)",
    "volume_0209_sum": "Seasonal summed water supply volume (Feb-Sep)",
    "volume_0307_sum": "Seasonal summed water supply volume (Mar-Jul)",
    "volume_0309_sum": "Seasonal summed water supply volume (Mar-Sep)",
    "volume_0406_sum": "Seasonal summed water supply volume (Apr-Jun)",
    "volume_0407_sum": "Seasonal summed water supply volume (Apr-Jul)",
    "volume_0409_sum": "Seasonal summed water supply volume (Apr-Sep)",
    "volume_monthly_sum": "Monthly summed water supply volume",
    # Cumulative sum observations (computed from monthly data)
    # Only generated for actual full forecast periods present in data
    "volume_0207_cumsum": "Cumulative water supply volume (Feb-Jul)",
    "volume_0209_cumsum": "Cumulative water supply volume (Feb-Sep)",
    "volume_0307_cumsum": "Cumulative water supply volume (Mar-Jul)",
    "volume_0309_cumsum": "Cumulative water supply volume (Mar-Sep)",
    "volume_0406_cumsum": "Cumulative water supply volume (Apr-Jun)",
    "volume_0407_cumsum": "Cumulative water supply volume (Apr-Jul)",
    "volume_0409_cumsum": "Cumulative water supply volume (Apr-Sep)",
}

# Internal mapping for handling truncated forecast variants during reconstruction
# Maps truncated periods to their full period equivalents
# E.g., 0507 (May-Jul) is a truncated variant of 0407 (Apr-Jul)
TRUNCATED_TO_FULL_PERIOD_MAP: dict[tuple[int, int], tuple[int, int]] = {
    (5, 6): (4, 6),  # May-Jun → Apr-Jun
    (5, 7): (4, 7),  # May-Jul → Apr-Jul
    (5, 9): (4, 9),  # May-Sep → Apr-Sep
    (6, 6): (4, 6),  # Jun-Jun → Apr-Jun
    (6, 7): (4, 7),  # Jun-Jul → Apr-Jul
    (6, 9): (4, 9),  # Jun-Sep → Apr-Sep
    (7, 9): (4, 9),  # Jul-Sep → Apr-Sep
    # Additional mappings for other start periods
    (3, 7): (2, 7),  # Mar-Jul → Feb-Jul
    (3, 9): (2, 9),  # Mar-Sep → Feb-Sep
    (4, 7): (3, 7),  # Apr-Jul → Mar-Jul
    (4, 9): (3, 9),  # Apr-Sep → Mar-Sep
}

# Forecast variable mapping for filtering (includes truncated variants that will be retagged)
# This is used only for filtering raw API data - truncated variants are retagged during reconstruction
_NRCS_FORECAST_FILTERING_MAP: dict[str, str] = {
    **NRCS_VARIABLE_MAPPING,  # Include all warehouse-valid variables
    # Add truncated variants for internal processing (not stored in warehouse)
    "volume_0506_sum": "Seasonal summed water supply volume (May-Jun)",
    "volume_0507_sum": "Seasonal summed water supply volume (May-Jul)",
    "volume_0509_sum": "Seasonal summed water supply volume (May-Sep)",
    "volume_0607_sum": "Seasonal summed water supply volume (Jun-Jul)",
    "volume_0609_sum": "Seasonal summed water supply volume (Jun-Sep)",
    "volume_0709_sum": "Seasonal summed water supply volume (Jul-Sep)",
}

sim_cols_raw = list(secondary_timeseries_schema(type="pandas").columns.keys())
obs_cols_raw = list(primary_timeseries_schema(type="pandas").columns.keys())
cols_to_remove = ["created_at", "updated_at"]

_OBSERVED_COLUMNS = [x for x in obs_cols_raw if x not in cols_to_remove]
_FORECAST_COLUMNS = [x for x in sim_cols_raw if x not in cols_to_remove]


def _configuration_for_element_code(
    element_code: str | None,
    *,
    configuration_name: str,
) -> str | None:
    """Resolve an element within the requested forecast or observation workflow."""
    if element_code in CONFIG_TO_ELEMENT_MAPPING.get(configuration_name, []):
        return configuration_name
    return None


def _conversion_for_unit_code(
    element_code: str | None,
    unit_code: str | None,
) -> float | None:
    """Select an element's permitted conversion using the response unit code."""
    if element_code is None:
        return None
    
    variable_config = ELEMENT_TO_VARIABLE_MAPPING.get(element_code)
    if variable_config is None:
        return None
    
    allowed_conversions = variable_config.get("conversion")

    if allowed_conversions is None:
        return None

    if unit_code == variable_config["target_unit"]:
        return None

    conversion = UNIT_CODE_TO_CONVERSION_MAPPING.get(unit_code)
    if conversion is None:
        raise ValueError(
            f"No conversion configured for elementCode {element_code!r} "
            f"with unitCode {unit_code!r}."
        )

    if conversion not in allowed_conversions:
        raise ValueError(
            f"Conversion for unitCode {unit_code!r} is not permitted "
            f"for elementCode {element_code!r}."
        )

    return conversion


def _apply_unit_conversions(df: pd.DataFrame) -> pd.DataFrame:
    """Convert values in place using each row's element and source unit."""
    combinations = df[["_element_code", "unit_name"]].drop_duplicates()

    for element_code, source_unit in combinations.itertuples(
        index=False, name=None
    ):
        conversion = _conversion_for_unit_code(element_code, source_unit)
        if conversion is None:
            continue

        mask = df["_element_code"].eq(element_code) & df["unit_name"].eq(source_unit)
        df.loc[mask, "value"] = df.loc[mask, "value"] * conversion
        df.loc[mask, "unit_name"] = ELEMENT_TO_VARIABLE_MAPPING[element_code][
            "target_unit"
        ]

    return df


def _parse_forecast_period(
    forecast_period: Sequence[str] | None,
) -> tuple[datetime, datetime]:
    """Validate and parse an MM-DD forecast-period pair."""
    if (
        not isinstance(forecast_period, Sequence)
        or isinstance(forecast_period, (str, bytes))
        or len(forecast_period) != 2
    ):
        raise ValueError(
            "forecastPeriod must be a two-item sequence of MM-DD strings."
        )

    try:
        start = datetime.strptime(f"{forecast_period[0]}-2000", "%m-%d-%Y")
        end = datetime.strptime(f"{forecast_period[1]}-2000", "%m-%d-%Y")
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid forecastPeriod: {forecast_period!r}; "
            "expected two MM-DD strings."
        ) from error

    if start.month == end.month and end.day < start.day:
        raise ValueError(
            f"forecastPeriod end precedes its start: {forecast_period!r}"
        )

    return start, end


def _forecast_period_metadata(
    element_code: str,
    forecast_period: Sequence[str] | None,
    water_year: int,
) -> tuple[str, pd.Timestamp]:
    """Build a forecast variable name and timestamp from one record's period."""
    start, end = _parse_forecast_period(forecast_period)

    start_month = f"{start.month:02d}"
    end_month = f"{end.month:02d}"

    variable_config = ELEMENT_TO_VARIABLE_MAPPING[element_code]
    variable_name = (
        f"{variable_config['parameter']}_"
        f"{start_month}{end_month}_"
        f"{variable_config['statistic']}"
    )

    start_year = water_year - (1 if start.month >= 10 else 0)
    try:
        value_time = pd.Timestamp(
            year=start_year,
            month=start.month,
            day=start.day,
        )
    except ValueError as error:
        raise ValueError(
            f"forecastPeriod start {forecast_period[0]!r} "
            f"is invalid for year {start_year}."
        ) from error

    return variable_name, value_time


def _latest_forecast_revisions(
    forecast_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the latest issue per element, publication date, and exact period.

    Called separately for each station. Valid issue dates outrank missing dates.
    Equal issue dates, or two missing issue dates, retain the last API record.
    """
    latest_items: dict[
        tuple[str | None, pd.Timestamp, tuple[int, int, int, int]],
        tuple[Any, dict[str, Any]],
    ] = {}

    for item in forecast_items:
        publication_time = pd.to_datetime(
            item.get("publicationDate"), errors="coerce", utc=True
        )
        if pd.isna(publication_time):
            continue

        start, end = _parse_forecast_period(item.get("forecastPeriod"))
        period_key = (start.month, start.day, end.month, end.day)
        key = (item.get("elementCode"), publication_time, period_key)

        issue_time = pd.to_datetime(
            item.get("issueDate"), errors="coerce", utc=True
        )
        existing = latest_items.get(key)

        if (
            existing is None
            or pd.isna(existing[0])
            or (pd.notna(issue_time) and issue_time >= existing[0])
        ):
            latest_items[key] = (issue_time, item)

    return [item for _, item in latest_items.values()]


def _format_rows(
    rows: list[dict[str, Any]],
    *,
    include_member: bool,
) -> pd.DataFrame:
    """Build the output schema and normalize timestamps, values, and units."""
    columns = _FORECAST_COLUMNS if include_member else _OBSERVED_COLUMNS
    df = pd.DataFrame(rows, columns=columns + ["_element_code"])

    df["reference_time"] = (
        pd.to_datetime(df["reference_time"], errors="coerce", utc=True).dt.tz_convert(
            None
        )
    )

    df["value_time"] = (
        pd.to_datetime(df["value_time"], errors="coerce", utc=True).dt.tz_convert(None)
    )

    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)

    if not df.empty:
        df = _apply_unit_conversions(df)

    return df[columns].reset_index(drop=True)


def _trim_date_window(
    df: pd.DataFrame,
    *,
    time_column: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """Trim timestamps to the requested window, including date-only end days."""
    if start_date is not None:
        df = df.loc[df[time_column] >= pd.Timestamp(start_date)]

    if end_date is not None:
        end_time = pd.Timestamp(end_date)
        if end_time == end_time.floor("D") and len(str(end_date).strip()) <= 10:
            df = df.loc[df[time_column].dt.floor("D") <= end_time]
        else:
            df = df.loc[df[time_column] <= end_time]

    return df.reset_index(drop=True)


def _forecasts_to_dataframe(
    forecast_response: list[dict[str, Any]] | _ForecastResponse,
    *,
    begin_publication_date: str | None = None,
    end_publication_date: str | None = None,
) -> pd.DataFrame:
    """Format forecast-endpoint records using their individual forecastPeriod."""
    configuration_name = "nrcs_adjusted_forecast"

    if begin_publication_date is None:
        begin_publication_date = getattr(
            forecast_response, "begin_publication_date", None
        )
    if end_publication_date is None:
        end_publication_date = getattr(
            forecast_response, "end_publication_date", None
        )

    rows: list[dict[str, Any]] = []

    for station_payload in forecast_response or []:
        station_triplet = station_payload.get("stationTriplet")
        location_id = f"nrcs-{station_triplet}" if station_triplet else None

        mapped_items = [
            item
            for item in station_payload.get("data") or []
            if (
                _configuration_for_element_code(
                    item.get("elementCode"),
                    configuration_name=configuration_name,
                )
                is not None
                and item.get("elementCode") in ELEMENT_TO_VARIABLE_MAPPING
            )
        ]

        for item in _latest_forecast_revisions(mapped_items):
            element_code = item["elementCode"]
            publication_time = pd.to_datetime(
                item.get("publicationDate"), errors="coerce"
            )
            if pd.isna(publication_time):
                continue

            variable_name, value_time = _forecast_period_metadata(
                element_code,
                item.get("forecastPeriod"),
                _water_year(publication_time),
            )

            row_base = {
                "reference_time": publication_time,
                "value_time": value_time,
                "variable_name": variable_name,
                "configuration_name": configuration_name,
                "unit_name": item.get("unitCode"),
                "location_id": location_id,
                "_element_code": element_code,
            }

            rows.append(
                {
                    **row_base,
                    "member": "mean",
                    "value": item.get("periodNormal"),
                }
            )

            for member, value in (item.get("forecastValues") or {}).items():
                rows.append(
                    {
                        **row_base,
                        "member": str(member),
                        "value": value,
                    }
                )

    df = _format_rows(rows, include_member=True)
    return _trim_date_window(
        df,
        time_column="reference_time",
        start_date=begin_publication_date,
        end_date=end_publication_date,
    )


def _observed_to_dataframe(
    observed_response: list[dict[str, Any]] | _DataResponse,
) -> pd.DataFrame:
    """Format monthly SRVO observations independently of forecast data."""
    configuration_name = "nrcs_adjusted_observed"
    rows: list[dict[str, Any]] = []

    for station_payload in observed_response or []:
        station_triplet = station_payload.get("stationTriplet")
        location_id = f"nrcs-{station_triplet}" if station_triplet else None

        for data_item in station_payload.get("data") or []:
            station_element = data_item.get("stationElement") or {}
            element_code = station_element.get("elementCode")

            if (
                _configuration_for_element_code(
                    element_code,
                    configuration_name=configuration_name,
                )
                is None
                or element_code not in ELEMENT_TO_VARIABLE_MAPPING
            ):
                continue

            if data_item.get("error"):
                raise ValueError(
                    f"Observation API error for {location_id!r}, "
                    f"elementCode {element_code!r}: {data_item['error']}"
                )

            if station_element.get("durationName") != "MONTHLY":
                raise ValueError(
                    "Observation formatting currently supports MONTHLY data only; "
                    f"received {station_element.get('durationName')!r} "
                    f"for {location_id!r}, elementCode {element_code!r}."
                )

            for observation in data_item.get("values") or []:
                try:
                    value_time = pd.Timestamp(
                        year=observation["year"],
                        month=observation["month"],
                        day=1,
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"Invalid monthly observation date for {location_id!r}: "
                        f"year={observation.get('year')!r}, "
                        f"month={observation.get('month')!r}."
                    ) from error

                rows.append(
                    {
                        "reference_time": pd.NaT,
                        "value_time": value_time,
                        "value": observation.get("value"),
                        "variable_name": "volume_monthly_sum",
                        "configuration_name": configuration_name,
                        "unit_name": station_element.get("storedUnitCode"),
                        "location_id": location_id,
                        "_element_code": element_code,
                    }
                )

    return _format_rows(rows, include_member=False)


def _validate_fetch_inputs(
    start_date: str,
    end_date: str,
    location_ids: str | list[str],
) -> list[str]:
    """Validate and normalize input parameters for fetch operations."""
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a YYYY-MM-DD string.")

        try:
            parsed_date = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(f"{name} must be a valid YYYY-MM-DD date.") from error

        if parsed_date.strftime("%Y-%m-%d") != value:
            raise ValueError(f"{name} must use the exact YYYY-MM-DD format.")

    if start_date > end_date:
        raise ValueError("start_date must not be later than end_date.")

    if isinstance(location_ids, str):
        location_ids = [location_ids]
    if not isinstance(location_ids, list):
        raise TypeError("location_ids must be a string or list of strings.")

    normalized_ids: list[str] = []
    for location_id in location_ids:
        if not isinstance(location_id, str):
            raise TypeError("Each location_id must be a string.")

        station_triplet = _normalize_station_triplet(location_id)
        parts = station_triplet.split(":")
        if (
            len(parts) != 3
            or not all(part.strip() for part in parts)
            or any(character in station_triplet for character in (",", "*"))
        ):
            raise ValueError(f"Invalid NRCS location_id: {location_id!r}.")

        normalized_id = f"nrcs-{station_triplet}"
        if normalized_id not in normalized_ids:
            normalized_ids.append(normalized_id)

    return normalized_ids


def _combine_location_frames(
    frames: list[pd.DataFrame],
    *,
    include_member: bool,
) -> pd.DataFrame:
    """Combine DataFrames from multiple locations into a single DataFrame."""
    columns = _FORECAST_COLUMNS if include_member else _OBSERVED_COLUMNS
    nonempty_frames = [frame for frame in frames if not frame.empty]

    if nonempty_frames:
        return pd.concat(nonempty_frames, ignore_index=True)[columns]

    return _format_rows([], include_member=include_member)


def _filter_unmapped_variables(
    df: pd.DataFrame,
    *,
    variable_mapping: dict[str, str],
) -> pd.DataFrame:
    """Filter dataframe to only include variables in the mapping.

    Issues a warning for any variables that are filtered out.

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
            f"The following variables were not found in NRCS_VARIABLE_MAPPING "
            f"and will be filtered out: {sorted(unmapped_vars)}",
            UserWarning,
            stacklevel=3,
        )
        df = df[df["variable_name"].isin(variable_mapping.keys())].reset_index(
            drop=True
        )

    return df


# =============================================================================
# Public API Functions
# =============================================================================


def fetch_nrcs_forecasts(
    start_date: str,
    end_date: str,
    location_ids: str | list[str],
) -> pd.DataFrame:
    """Fetch SRVO forecasts within an inclusive publication-date window.

    Each record supplies its own forecast period. Values are converted to m^3.
    Distinct periods sharing a publication date remain separate.

    Data is filtered to only include variables defined in NRCS_VARIABLE_MAPPING.
    A warning is issued for any variables that are filtered out.

    Parameters
    ----------
    start_date : str
        Start of publication-date window (YYYY-MM-DD format)
    end_date : str
        End of publication-date window (YYYY-MM-DD format)
    location_ids : str | list[str]
        One or more NRCS location IDs (station triplets, with or without 'nrcs-' prefix)

    Returns
    -------
    pd.DataFrame
        Secondary timeseries with forecasts, unit-converted to m^3
    """
    normalized_ids = _validate_fetch_inputs(start_date, end_date, location_ids)
    frames: list[pd.DataFrame] = []

    for location_id in normalized_ids:
        response = _get_forecasts(
            station_triplets=location_id,
            element_codes=CONFIG_TO_ELEMENT_MAPPING["nrcs_adjusted_forecast"],
            begin_publication_date=start_date,
            end_publication_date=end_date,
            expand_water_years=False,
        )
        frames.append(_forecasts_to_dataframe(response))

    df = _combine_location_frames(frames, include_member=True)
    return _filter_unmapped_variables(df, variable_mapping=_NRCS_FORECAST_FILTERING_MAP)


def fetch_nrcs_observations(
    start_date: str,
    end_date: str,
    location_ids: str | list[str],
) -> pd.DataFrame:
    """Fetch monthly SRVO observations within an inclusive value-time window.

    reference_time is NaT; value_time is the observation month start.
    No forecast requests, seasonal aggregation, or seasonal filtering occur.

    Data is filtered to only include variables defined in NRCS_VARIABLE_MAPPING.
    A warning is issued for any variables that are filtered out.

    Parameters
    ----------
    start_date : str
        Start of value-time window (YYYY-MM-DD format)
    end_date : str
        End of value-time window (YYYY-MM-DD format)
    location_ids : str | list[str]
        One or more NRCS location IDs (station triplets, with or without 'nrcs-' prefix)

    Returns
    -------
    pd.DataFrame
        Primary timeseries with observations, unit-converted to m^3
    """
    normalized_ids = _validate_fetch_inputs(start_date, end_date, location_ids)
    frames: list[pd.DataFrame] = []

    for location_id in normalized_ids:
        response = _get_data(
            station_triplets=location_id,
            elements=CONFIG_TO_ELEMENT_MAPPING["nrcs_adjusted_observed"],
            duration="MONTHLY",
            begin_date=start_date,
            end_date=end_date,
        )
        frame = _observed_to_dataframe(response)
        frames.append(
            _trim_date_window(
                frame,
                time_column="value_time",
                start_date=start_date,
                end_date=end_date,
            )
        )

    df = _combine_location_frames(frames, include_member=False)
    return _filter_unmapped_variables(df, variable_mapping=NRCS_VARIABLE_MAPPING)


# =============================================================================
# Per-Location Sequential Processing Functions
# =============================================================================


def _identify_forecast_periods_per_location(
    forecast_df: pd.DataFrame,
) -> dict[str, list[tuple[int, int]]]:
    """Identify unique full forecast periods for each location.
    
    Parses forecast variable names to find the unique (start_month, end_month)
    tuples present in each location's forecast data. The full period is identified
    as the earliest start_month for each end_month.
    
    Parameters
    ----------
    forecast_df : pd.DataFrame
        DataFrame with columns: location_id, variable_name, ...
        variable_name format: "volume_MMDD_sum" where MM=start_month, DD=end_month
    
    Returns
    -------
    dict[str, list[tuple[int, int]]]
        Mapping of location_id → list of (start_month, end_month) tuples
        representing full forecast periods for that location.
    """
    if forecast_df.empty:
        return {}
    
    result: dict[str, list[tuple[int, int]]] = {}
    
    for location_id in forecast_df["location_id"].unique():
        location_forecasts = forecast_df[forecast_df["location_id"] == location_id]
        periods_by_end: dict[int, list[int]] = {}
        
        for var_name in location_forecasts["variable_name"].unique():
            if not isinstance(var_name, str) or "_" not in var_name:
                continue
            
            parts = var_name.split("_")
            mmdd = parts[1] if len(parts) > 1 else None
            
            if not mmdd or len(mmdd) < 4:
                continue
            
            try:
                start_month = int(mmdd[0:2])
                end_month = int(mmdd[2:4])
                if end_month not in periods_by_end:
                    periods_by_end[end_month] = []
                if start_month not in periods_by_end[end_month]:
                    periods_by_end[end_month].append(start_month)
            except ValueError:
                continue
        
        # Build full periods (earliest start for each end)
        full_periods = []
        for end_month, start_months in sorted(periods_by_end.items()):
            full_start = min(start_months)
            full_periods.append((full_start, end_month))
        
        result[location_id] = sorted(full_periods)
    
    return result


def _generate_observed_cumsum(
    location_obs_df: pd.DataFrame,
    periods: list[tuple[int, int]],
    location_id: str,
) -> pd.DataFrame:
    """Generate cumulative sum observations for one location's forecast periods.
    
    For each forecast period (start_month, end_month), calculates cumulative sum
    of observations, including ONLY observations with value_time.month within
    the period's month range. Cumsum starts from 0 at the period start month.
    
    Parameters
    ----------
    location_obs_df : pd.DataFrame
        Observations for this location: columns location_id, value_time, value,
        unit_name, _element_code (optional)
    periods : list[tuple[int, int]]
        List of (start_month, end_month) tuples representing full forecast periods
    location_id : str
        The location_id for this location
    
    Returns
    -------
    pd.DataFrame
        Cumsum timeseries with variable_name: volume_MMDD_cumsum,
        configuration_name: nrcs_adjusted_observed
    """
    if location_obs_df.empty or not periods:
        return pd.DataFrame(columns=_OBSERVED_COLUMNS)
    
    rows: list[dict[str, Any]] = []
    location_obs = location_obs_df.sort_values("value_time").reset_index(drop=True)
    
    for start_month, end_month in periods:
        # Filter observations that fall within [start_month, end_month] range
        relevant_obs = []
        for _, obs_row in location_obs.iterrows():
            month = obs_row["value_time"].month
            if start_month <= end_month:
                # Normal case: e.g., Apr-Jul (04-07)
                if start_month <= month <= end_month:
                    relevant_obs.append(obs_row)
            else:
                # Wrapped case: e.g., Oct-Feb (10-02)
                if month >= start_month or month <= end_month:
                    relevant_obs.append(obs_row)
        
        if not relevant_obs:
            continue
        
        # Build cumsum timeseries
        cumsum_value = 0.0
        for obs in relevant_obs:
            cumsum_value += obs["value"]
            rows.append({
                "reference_time": pd.NaT,
                "value_time": obs["value_time"],
                "value": cumsum_value,
                "variable_name": f"volume_{start_month:02d}{end_month:02d}_cumsum",
                "configuration_name": "nrcs_adjusted_observed",
                "unit_name": obs["unit_name"],
                "location_id": location_id,
                "_element_code": obs.get("_element_code"),
            })
        
        # Add initial zero point at period start if first observation is after period start
        if relevant_obs:
            first_obs_month = relevant_obs[0]["value_time"].month
            first_obs_year = relevant_obs[0]["value_time"].year
            if first_obs_month > start_month or (first_obs_month == start_month and 
                                                   relevant_obs[0]["value_time"].day > 1):
                period_start = pd.Timestamp(year=first_obs_year, month=start_month, day=1)
                # Only add zero point if it's before the first observation
                if period_start < relevant_obs[0]["value_time"]:
                    rows.insert(0, {
                        "reference_time": pd.NaT,
                        "value_time": period_start,
                        "value": 0.0,
                        "variable_name": f"volume_{start_month:02d}{end_month:02d}_cumsum",
                        "configuration_name": "nrcs_adjusted_observed",
                        "unit_name": location_obs.iloc[0]["unit_name"],
                        "location_id": location_id,
                        "_element_code": location_obs.iloc[0].get("_element_code"),
                    })
    
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_OBSERVED_COLUMNS)


def _extract_final_observed_from_cumsum(
    location_cumsum_df: pd.DataFrame,
    periods: list[tuple[int, int]],
    location_id: str,
) -> pd.DataFrame:
    """Extract final observed values from cumsum timeseries.
    
    For each forecast period, extracts the last (final) cumsum value and retaggs
    it from volume_MMDD_cumsum to volume_MMDD_sum. This represents the final
    total observed value for the entire forecast period.
    
    Parameters
    ----------
    location_cumsum_df : pd.DataFrame
        Cumsum observations for this location (output from _generate_observed_cumsum)
    periods : list[tuple[int, int]]
        List of (start_month, end_month) tuples
    location_id : str
        The location_id
    
    Returns
    -------
    pd.DataFrame
        One row per period with the final cumsum value, retagged as _sum variable
    """
    if location_cumsum_df.empty or not periods:
        return pd.DataFrame(columns=_OBSERVED_COLUMNS)
    
    rows: list[dict[str, Any]] = []
    
    for start_month, end_month in periods:
        var_name = f"volume_{start_month:02d}{end_month:02d}_cumsum"
        period_cumsum = location_cumsum_df[
            location_cumsum_df["variable_name"] == var_name
        ]
        
        if period_cumsum.empty:
            continue
        
        # Get the last (final) cumsum value for this period
        final_row = period_cumsum.sort_values("value_time").iloc[-1].copy()
        
        # Retag from _cumsum to _sum
        final_row["variable_name"] = f"volume_{start_month:02d}{end_month:02d}_sum"
        rows.append(final_row)
    
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_OBSERVED_COLUMNS)


def _process_location_forecasts(
    location_forecasts_df: pd.DataFrame,
    location_cumsum_df: pd.DataFrame,
    periods: list[tuple[int, int]],
    location_id: str,
) -> pd.DataFrame:
    """Process forecasts for one location with Cases A/B/C retagging and reconstruction.
    
    Applies three-case logic to all forecast entries:
    - **Case A (Full period):** volume_MMDD_sum → keep as volume_MMDD_sum, use value directly
    - **Case B (Earlier month):** volume_MMCC_sum (earlier month, same end) → retag to 
      volume_MMDD_sum (full period), use value directly
    - **Case C (Truncated):** volume_NNDD_sum (truncated, same end) → retag to 
      volume_MMDD_sum (full period), reconstruct value using cumsum of previous month
    
    Parameters
    ----------
    location_forecasts_df : pd.DataFrame
        Forecasts for this location: location_id, reference_time, value_time, value,
        variable_name, member, configuration_name, unit_name, _element_code (optional)
    location_cumsum_df : pd.DataFrame
        Cumsum observations for this location (for Case C reconstruction)
    periods : list[tuple[int, int]]
        List of (start_month, end_month) tuples representing full periods
    location_id : str
        The location_id
    
    Returns
    -------
    pd.DataFrame
        Processed forecasts with retagged variable_names and reconstructed values
    """
    if location_forecasts_df.empty or not periods:
        return location_forecasts_df[[]].copy()
    
    # Create a mapping of end_month → full period start_month
    end_to_full_start: dict[int, int] = {}
    for start_month, end_month in periods:
        end_to_full_start[end_month] = start_month
    
    output_rows: list[dict[str, Any]] = []
    
    for _, row in location_forecasts_df.iterrows():
        var_name = row["variable_name"]
        
        # Parse variable name
        if not isinstance(var_name, str) or "_" not in var_name:
            continue
        
        parts = var_name.split("_")
        mmdd = parts[1] if len(parts) > 1 else None
        
        if not mmdd or len(mmdd) < 4:
            continue
        
        try:
            this_start_month = int(mmdd[0:2])
            this_end_month = int(mmdd[2:4])
        except (ValueError, IndexError):
            continue
        
        # Check if this end_month has a full period
        if this_end_month not in end_to_full_start:
            continue
        
        full_start_month = end_to_full_start[this_end_month]
        full_var_name = f"volume_{full_start_month:02d}{this_end_month:02d}_sum"
        
        # Apply three-case logic
        output_row = row.copy()
        output_row["variable_name"] = full_var_name
        
        if this_start_month == full_start_month:
            # Case A: Full period - use value directly
            reconstructed_value = row["value"]
        elif this_start_month < full_start_month:
            # Case B: Earlier month forecast - use value directly (no cumsum offset)
            reconstructed_value = row["value"]
        else:
            # Case C: Truncated variant - add previous month's cumsum and adjust value_time
            # e.g., if forecast starts in May (05), previous is April (04)
            previous_month = this_start_month - 1
            if previous_month == 0:
                previous_month = 12
            
            cumsum_var_name = f"volume_{full_start_month:02d}{this_end_month:02d}_cumsum"
            cumsum_matches = location_cumsum_df[
                (location_cumsum_df["variable_name"] == cumsum_var_name) &
                (location_cumsum_df["value_time"].dt.month == previous_month)
            ]
            
            if not cumsum_matches.empty:
                # Get the latest cumsum value for the previous month
                cumsum_matches = cumsum_matches.sort_values("value_time", ascending=False)
                prev_cumsum_value = cumsum_matches.iloc[0]["value"]
                reconstructed_value = prev_cumsum_value + row["value"]
            else:
                # No cumsum available, use forecast value directly (fallback)
                reconstructed_value = row["value"]
            
            # Adjust value_time to the start month of the full period
            # Get the year from current value_time, then set to start_month
            current_value_time = pd.Timestamp(row["value_time"])
            output_row["value_time"] = current_value_time.replace(month=full_start_month, day=1)
        
        output_row["value"] = reconstructed_value
        output_rows.append(output_row)
    
    return pd.DataFrame(output_rows)[_FORECAST_COLUMNS] if output_rows else pd.DataFrame(columns=_FORECAST_COLUMNS)


__all__ = ["fetch_nrcs_forecasts", "fetch_nrcs_observations", "NRCS_VARIABLE_MAPPING"]
