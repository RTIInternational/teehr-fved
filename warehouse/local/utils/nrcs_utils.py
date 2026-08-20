"""Utilities for interacting with the NRCS AWDB REST API.

API docs: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html#/
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
DEFAULT_TIMEOUT = 60
KAC_FT_TO_M3 = 1_233_481.83754752


def _normalize_station_triplet(station_triplet: str) -> str:
	"""Normalize station IDs, allowing inputs like 'nrcs-09361500:CO:USGS'."""
	cleaned = station_triplet.strip()
	if cleaned.lower().startswith("nrcs-"):
		cleaned = cleaned[5:]
	return cleaned


def _to_csv(value: str | Sequence[str] | None, *, normalize_station_triplets: bool = False) -> str | None:
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
	return {k: v for k, v in params.items() if v is not None and v != ""}


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


def get_stations(
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
) -> list[dict[str, Any]]:
	"""Get station metadata from `/services/v1/stations`.

	The API expects many list-like inputs as comma-separated strings.
	"""
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
	return _get("stations", params, timeout=timeout)


def get_data(
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
) -> list[dict[str, Any]]:
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
	return _get("data", params, timeout=timeout)


def get_forecasts(
	station_triplets: str | Sequence[str],
	*,
	element_codes: str | Sequence[str] | None = None,
	begin_publication_date: str | None = None,
	end_publication_date: str | None = None,
	exceedence_probabilities: str | Sequence[str | int] | None = None,
	forecast_periods: str | Sequence[str] | None = None,
	timeout: int = DEFAULT_TIMEOUT,
	**extra_params: Any,
) -> list[dict[str, Any]]:
	"""Get forecast data from `/services/v1/forecasts`."""
	params = {
		"stationTriplets": _to_csv(station_triplets, normalize_station_triplets=True),
		"elementCodes": _to_csv(element_codes),
		"beginPublicationDate": begin_publication_date,
		"endPublicationDate": end_publication_date,
		"exceedenceProbabilities": _to_csv(exceedence_probabilities),
		"forecastPeriods": _to_csv(forecast_periods),
	}
	params.update(extra_params)
	return _get("forecasts", params, timeout=timeout)


def forecasts_to_dataframe(
	forecast_response: list[dict[str, Any]],
	*,
	variable_prefix: str = "wsv_forecast_",
	quantiles: Sequence[str] = ("90", "70", "50", "30", "10"),
	convert_kac_ft_to_m3: bool = True,
) -> pd.DataFrame:
	"""Convert AWDB forecast response into the ingest schema.

	Output columns:
	[reference_time, value_time, value, variable_name, configuration_name,
	 unit_name, location_id, member]
	"""
	rows: list[dict[str, Any]] = []

	for station_payload in forecast_response or []:
		station_triplet = station_payload.get("stationTriplet")
		location_id = f"nrcs-{station_triplet}" if station_triplet else None

		for forecast_item in station_payload.get("data", []):
			publication_date = forecast_item.get("publicationDate")
			period_normal = forecast_item.get("periodNormal")
			forecast_values = forecast_item.get("forecastValues") or {}

			row_base = {
				"reference_time": publication_date,
				"value_time": publication_date,
				"configuration_name": "nrcs_wsv_seasonal_forecast",
				"unit_name": forecast_item.get("unitCode"),
				"location_id": location_id,
				"member": None,
			}

			rows.append(
				{
					**row_base,
					"variable_name": f"{variable_prefix}mean",
					"value": period_normal,
				}
			)

			for q in quantiles:
				rows.append(
					{
						**row_base,
						"variable_name": f"{variable_prefix}{q}",
						"value": forecast_values.get(str(q)),
					}
				)

	df = pd.DataFrame(rows)
	if df.empty:
		return pd.DataFrame(
			columns=[
				"reference_time",
				"value_time",
				"value",
				"variable_name",
				"configuration_name",
				"unit_name",
				"location_id",
				"member",
			]
		)

	df["reference_time"] = pd.to_datetime(df["reference_time"], errors="coerce")
	df["value_time"] = pd.to_datetime(df["value_time"], errors="coerce")
	df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)

	if convert_kac_ft_to_m3:
		mask = df["unit_name"].eq("kac_ft") & df["value"].notna()
		df.loc[mask, "value"] = df.loc[mask, "value"] * KAC_FT_TO_M3
		df.loc[df["unit_name"].eq("kac_ft"), "unit_name"] = "m^3"

	return df[
		[
			"reference_time",
			"value_time",
			"value",
			"variable_name",
			"configuration_name",
			"unit_name",
			"location_id",
			"member",
		]
	]
