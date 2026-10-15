"""Fetching and formatting utilities for NRCS AWDB data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pandas as pd

from . import nrcs_api_accessor as _api_accessor
from .nrcs_api_accessor import _water_year

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

_OBSERVED_COLUMNS = [
    "reference_time",
    "value_time",
    "value",
    "variable_name",
    "configuration_name",
    "unit_name",
    "location_id",
]
_FORECAST_COLUMNS = _OBSERVED_COLUMNS + ["member"]


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
    element_code: str,
    unit_code: str | None,
) -> float | None:
    """Select an element's permitted conversion using the response unit code."""
    variable_config = ELEMENT_TO_VARIABLE_MAPPING[element_code]
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

    month_codes: list[str] = []
    month = start.month
    while True:
        month_codes.append(MONTH_INITIALS[month - 1])
        if month == end.month:
            break
        month = month % 12 + 1

    variable_config = ELEMENT_TO_VARIABLE_MAPPING[element_code]
    variable_name = (
        f"{variable_config['parameter']}_"
        f"{''.join(month_codes)}_"
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

    df["reference_time"] = pd.to_datetime(df["reference_time"], errors="coerce")
    df["value_time"] = pd.to_datetime(df["value_time"], errors="coerce")
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
    forecast_response: list[dict[str, Any]] | _api_accessor._ForecastResponse,
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
    observed_response: list[dict[str, Any]] | _api_accessor._DataResponse,
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
                        "variable_name": "volume_monthly_inst",
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

        station_triplet = _api_accessor._normalize_station_triplet(location_id)
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
    columns = _FORECAST_COLUMNS if include_member else _OBSERVED_COLUMNS
    nonempty_frames = [frame for frame in frames if not frame.empty]

    if nonempty_frames:
        return pd.concat(nonempty_frames, ignore_index=True)[columns]

    return _format_rows([], include_member=include_member)


def fetch_nrcs_forecasts(
    start_date: str,
    end_date: str,
    location_ids: str | list[str],
) -> pd.DataFrame:
    """Fetch SRVO forecasts within an inclusive publication-date window.

    Each record supplies its own forecast period. Values are converted to m^3.
    Distinct periods sharing a publication date remain separate.
    """
    normalized_ids = _validate_fetch_inputs(start_date, end_date, location_ids)
    frames: list[pd.DataFrame] = []

    for location_id in normalized_ids:
        response = _api_accessor._get_forecasts(
            station_triplets=location_id,
            element_codes=CONFIG_TO_ELEMENT_MAPPING["nrcs_adjusted_forecast"],
            begin_publication_date=start_date,
            end_publication_date=end_date,
            expand_water_years=False,
        )
        frames.append(_forecasts_to_dataframe(response))

    return _combine_location_frames(frames, include_member=True)


def fetch_nrcs_observations(
    start_date: str,
    end_date: str,
    location_ids: str | list[str],
) -> pd.DataFrame:
    """Fetch monthly SRVO observations within an inclusive value-time window.

    reference_time is NaT; value_time is the observation month start.
    No forecast requests, seasonal aggregation, or seasonal filtering occur.
    """
    normalized_ids = _validate_fetch_inputs(start_date, end_date, location_ids)
    frames: list[pd.DataFrame] = []

    for location_id in normalized_ids:
        response = _api_accessor._get_data(
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

    return _combine_location_frames(frames, include_member=False)


__all__ = ["fetch_nrcs_forecasts", "fetch_nrcs_observations"]
