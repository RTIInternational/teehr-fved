"""Client accessor and response wrappers for interacting with the NRCS AWDB REST API.

API docs: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html#/
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
DEFAULT_TIMEOUT = 60


class _StationsResponse(list):
    """List of station metadata payloads with attached query parameters.

    Subclasses `list` so standard list operations, iteration, indexing,
    and `json.dumps()` continue to work natively.
    """

    def __init__(
        self,
        iterable: Sequence[dict[str, Any]] = (),
        *,
        query_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(iterable)
        self.query_params = query_params or {}


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


def _get_stations(
    station_triplets: str | Sequence[str] | None = None,
    *,
    station_names: str | Sequence[str] | None = None,
    dco_codes: str | Sequence[str] | None = None,
    county_names: str | Sequence[str] | None = None,
    elements: str | Sequence[str] | None = None,
    durations: str | Sequence[str] | None = None,
    hucs: str | Sequence[str] | None = None,
    return_forecast_point_metadata: bool = False,
    return_reservoir_metadata: bool = False,
    return_station_elements: bool = True,
    active_only: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    **extra_params: Any,
) -> _StationsResponse:
    """Get station metadata from `/services/v1/stations`."""
    params = {
        "stationTriplets": _to_csv(station_triplets, normalize_station_triplets=True),
        "stationNames": _to_csv(station_names),
        "dcoCodes": _to_csv(dco_codes),
        "countyNames": _to_csv(county_names),
        "elements": _to_csv(elements),
        "durations": _to_csv(durations),
        "hucs": _to_csv(hucs),
        "returnForecastPointMetadata": return_forecast_point_metadata,
        "returnReservoirMetadata": return_reservoir_metadata,
        "returnStationElements": return_station_elements,
        "activeOnly": active_only,
    }
    params.update(extra_params)
    raw_response = _get("stations", params, timeout=timeout)
    return _StationsResponse(raw_response or [], query_params=_clean_params(params))


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


__all__: list[str] = []