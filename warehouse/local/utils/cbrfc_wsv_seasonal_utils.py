import pandas as pd
import requests


CBRFC_SEASONAL_WSUP_URL = "https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py"
SIM_CONFIGURATION_NAME = "cbrfc_seasonal_wsv_forecast"
OBS_CONFIGURATION_NAME = "cbrfc_seasonal_wsv_observed"
SEASONAL_WSUP_UNIT_NAME = "m^3"
KAF_TO_CUBIC_METERS = 1000 * 1233.48184
OBS_RAW_KEY = "Obs"

SIM_SCHEMA_COLUMNS = [
	"reference_time",
	"value_time",
	"value",
	"variable_name",
	"configuration_name",
	"unit_name",
	"location_id",
	"member",
]

OBS_SCHEMA_COLUMNS = [
	"reference_time",
	"value_time",
	"value",
	"variable_name",
	"configuration_name",
	"unit_name",
	"location_id",
]

RAW_KEYS_TO_TEEHR_VARIABLES = {
	'max': 'wsv_esp_max',
	'p10': 'wsv_esp_p10',
    'p30': 'wsv_esp_p30',
	'p50': 'wsv_esp_p50',
    'p70': 'wsv_esp_p70',
	'p90': 'wsv_esp_p90',
	'min': 'wsv_esp_min',
	'crx': 'wsv_official_crx',
	'c30': 'wsv_official_c30',
	'cmp': 'wsv_official_cmp',
	'c70': 'wsv_official_c70',
	'crn': 'wsv_official_crn',
	'Obs': 'wsv_obs',
}


def _normalize_cbrfc_lid(site_id: str) -> str:
	"""
	Normalize a test location ID like 'cbrfc-OAWU1' to the CBRFC LID 'OAWU1'.
	"""
	if not isinstance(site_id, str) or not site_id.strip():
		raise ValueError("site_id must be a non-empty string")

	return site_id.strip().removeprefix("cbrfc-").upper()


def _build_seasonal_wsup_url(site_id: str, year: int) -> str:
	"""
	Build a CBRFC seasonal water supply forecast CSV URL for one site and year.
	"""
	lid = _normalize_cbrfc_lid(site_id)
	return f"{CBRFC_SEASONAL_WSUP_URL}?id={lid}&year={int(year)}&db=&csv=1"


def _is_parseable_number(value: str) -> bool:
	"""
	Return True when a raw CSV field can be interpreted as a numeric value.
	"""
	try:
		float(value)
	except (TypeError, ValueError):
		return False

	return True


def _parse_seasonal_wsup_csv_text(csv_text: str) -> pd.DataFrame:
	"""
	Parse CBRFC seasonal water supply forecast CSV text from the webpage.
	"""
	lines = [line.strip() for line in csv_text.splitlines()]
	header_index = next((index for index, line in enumerate(lines) if line.startswith("Run Date,")), None)
	if header_index is None:
		raise ValueError("Could not find CBRFC seasonal forecast CSV header")

	columns = lines[header_index].split(",")
	records = []

	for line in lines[header_index + 1:]:
		line = line.removesuffix("</pre>").strip()
		if not line:
			continue

		parts = [None if part in {"", "None"} else part for part in line.split(",")]
		if pd.isna(pd.to_datetime(parts[0], errors="coerce")):
			continue

		if len(parts) < len(columns):
			missing_count = len(columns) - len(parts)
			last_value = parts[-1]
			if last_value is not None and _is_parseable_number(last_value):
				parts = parts[:-1] + ([None] * missing_count) + [last_value]
			else:
				parts = parts + ([None] * missing_count)

		if len(parts) != len(columns):
			raise ValueError(f"Expected {len(columns)} columns but found {len(parts)} in row: {line}")

		records.append(parts)

	return pd.DataFrame(records, columns=columns)


def _split_seasonal_wsup_timeseries(
		forecast_df: pd.DataFrame,
		timestamp_column: str = "Run Date",
		) -> dict[str, pd.DataFrame]:
	"""
	Split a seasonal water supply forecast table into one DataFrame per timeseries.
	"""
	if timestamp_column not in forecast_df.columns:
		raise ValueError(f"Expected timestamp column '{timestamp_column}' in forecast data")

	clean_df = forecast_df.copy()
	clean_df[timestamp_column] = pd.to_datetime(clean_df[timestamp_column], errors="coerce")
	clean_df = clean_df.dropna(subset=[timestamp_column])

	timeseries = {}
	for column in clean_df.columns.drop(timestamp_column):
		series_df = clean_df[[timestamp_column, column]].copy()
		series_df[column] = (pd.to_numeric(series_df[column], errors="coerce") * KAF_TO_CUBIC_METERS).round(3)
		timeseries[column] = series_df.dropna(subset=[column]).reset_index(drop=True)

	return timeseries


def _format_seasonal_wsup_timeseries(
		raw_key: str,
		timeseries_df: pd.DataFrame,
		location_id: str,
		configuration_name: str,
		timestamp_column: str = "Run Date",
		include_member: bool = False,
		) -> pd.DataFrame:
	"""
	Format one raw CBRFC seasonal timeseries to the ingest schema.
	"""
	if raw_key not in RAW_KEYS_TO_TEEHR_VARIABLES:
		raise ValueError(f"No TEEHR variable mapping found for raw key '{raw_key}'")
	if timestamp_column not in timeseries_df.columns:
		raise ValueError(f"Expected timestamp column '{timestamp_column}' in {raw_key} timeseries")
	if raw_key not in timeseries_df.columns:
		raise ValueError(f"Expected value column '{raw_key}' in {raw_key} timeseries")

	formatted = pd.DataFrame({
		"reference_time": pd.NaT,
		"value_time": pd.to_datetime(timeseries_df[timestamp_column]),
		"value": pd.to_numeric(timeseries_df[raw_key], errors="raise").astype(float),
		"variable_name": RAW_KEYS_TO_TEEHR_VARIABLES[raw_key],
		"configuration_name": configuration_name,
		"unit_name": SEASONAL_WSUP_UNIT_NAME,
		"location_id": location_id,
	})

	if include_member:
		formatted["member"] = None
		return formatted[SIM_SCHEMA_COLUMNS]

	return formatted[OBS_SCHEMA_COLUMNS]


def _assemble_seasonal_wsup_site_data(
		timeseries: dict[str, pd.DataFrame],
		location_id: str,
		) -> dict[str, pd.DataFrame]:
	"""
	Assemble simulated and observed ingest DataFrames for one location.
	"""
	sim_frames = []
	obs_frames = []

	for raw_key, timeseries_df in timeseries.items():
		if raw_key == OBS_RAW_KEY:
			obs_frames.append(_format_seasonal_wsup_timeseries(
				raw_key=raw_key,
				timeseries_df=timeseries_df,
				location_id=location_id,
				configuration_name=OBS_CONFIGURATION_NAME,
			))
		else:
			sim_frames.append(_format_seasonal_wsup_timeseries(
				raw_key=raw_key,
				timeseries_df=timeseries_df,
				location_id=location_id,
				configuration_name=SIM_CONFIGURATION_NAME,
				include_member=True,
			))

	sim_df = pd.concat(sim_frames, ignore_index=True) if sim_frames else pd.DataFrame(columns=SIM_SCHEMA_COLUMNS)
	obs_df = pd.concat(obs_frames, ignore_index=True) if obs_frames else pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)

	return {"sim": sim_df, "obs": obs_df}


def _fetch_seasonal_wsup_timeseries(site_id: str, year: int, timeout: int = 30) -> dict[str, pd.DataFrame]:
	"""
	Fetch a CBRFC seasonal water supply forecast CSV page into timeseries DataFrames.
	"""
	url = _build_seasonal_wsup_url(site_id, year)

	try:
		response = requests.get(url, timeout=timeout)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise RuntimeError(f"Could not fetch CBRFC seasonal forecast from {url}: {exc}") from exc

	try:
		forecast_df = _parse_seasonal_wsup_csv_text(response.text)
	except ValueError as exc:
		raise ValueError(f"Could not parse CBRFC seasonal forecast CSV from {url}: {exc}") from exc

	return _split_seasonal_wsup_timeseries(forecast_df)


def _fetch_seasonal_wsup_site_results(
		location_ids: list[str],
		year: int,
		timeout: int = 30,
		) -> dict[str, dict[str, pd.DataFrame]]:
	"""
	Fetch and assemble seasonal water supply forecast data for multiple locations.
	"""
	results = {}

	for location_id in location_ids:
		timeseries = _fetch_seasonal_wsup_timeseries(location_id, year, timeout=timeout)
		results[location_id] = _assemble_seasonal_wsup_site_data(timeseries, location_id)

	return results


def _combine_seasonal_wsup_results(
		seasonal_results: dict[str, dict[str, pd.DataFrame]],
		) -> tuple[pd.DataFrame, pd.DataFrame]:
	"""
	Combine site-keyed seasonal forecast results into simulated and observed DataFrames.
	"""
	sim_frames = []
	obs_frames = []

	for location_id, site_results in seasonal_results.items():
		if "sim" not in site_results or "obs" not in site_results:
			raise ValueError(f"Expected 'sim' and 'obs' results for location '{location_id}'")

		sim_frames.append(site_results["sim"])
		obs_frames.append(site_results["obs"])

	sim_df = pd.concat(sim_frames, ignore_index=True) if sim_frames else pd.DataFrame(columns=SIM_SCHEMA_COLUMNS)
	obs_df = pd.concat(obs_frames, ignore_index=True) if obs_frames else pd.DataFrame(columns=OBS_SCHEMA_COLUMNS)

	return sim_df[SIM_SCHEMA_COLUMNS], obs_df[OBS_SCHEMA_COLUMNS]


def fetch_seasonal_wsup_forecasts(
		location_ids: list[str],
		year: int,
		timeout: int = 30,
		) -> tuple[pd.DataFrame, pd.DataFrame]:
	"""
	Fetch CBRFC seasonal forecasts and return final simulated and observed DataFrames.
	"""
	seasonal_results = _fetch_seasonal_wsup_site_results(location_ids, year, timeout=timeout)
	return _combine_seasonal_wsup_results(seasonal_results)
