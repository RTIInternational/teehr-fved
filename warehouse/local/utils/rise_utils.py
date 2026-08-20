import requests
import pandas as pd
from typing import Optional, Dict, Any


RISE_API_BASE_URL = "https://data.usbr.gov/rise/api"

_CFS_TO_CMS = 0.0283168

_DEFAULT_CONSTANT_FIELDS = {
    'reference_time': None,
    'variable_name': 'streamflow_daily_mean',
    'configuration_name': 'usbr_observations',
    'unit_name': 'm^3/s',
}

_OUTPUT_COLUMNS = [
    'reference_time', 
    'value_time', 
    'value',
    'variable_name', 
    'configuration_name', 
    'unit_name', 
    'location_id',
]


def _fetch_parameter_metadata(parameter_id: int, headers: Dict[str, str]) -> Dict[str, Any]:
    """Fetch and return parameter name, unit, and timestep for a given parameterId."""
    r = requests.get(f"{RISE_API_BASE_URL}/parameter/{parameter_id}", headers=headers, timeout=30)
    r.raise_for_status()
    attrs = r.json().get('data', {}).get('attributes', {})
    return {
        'parameter_name': attrs.get('parameterName'),
        'parameter_unit': attrs.get('parameterUnit'),
        'parameter_timestep': attrs.get('parameterTimestep'),
    }

def _parse_rise_id(rise_id: str) -> Dict[str, str]:
    """
    Parse a RISE location ID string into its component parts.
    
    Args:
        rise_id: Location ID in format 'rise-{location_id}-{record_id}-{item_id}'
        
    Returns:
        Dictionary with keys: location_id, record_id, item_id
        
    Example:
        >>> parse_rise_id('rise-392-2361-502')
        {'location_id': '392', 'record_id': '2361', 'item_id': '502'}
    """
    parts = rise_id.split('-')
    if len(parts) != 4 or parts[0] != 'rise':
        raise ValueError(
            f"Invalid RISE ID format: {rise_id}. "
            "Expected format: rise-{{location_id}}-{{record_id}}-{{item_id}}"
        )
    
    return {
        'location_id': parts[1],
        'record_id': parts[2],
        'item_id': parts[3]
    }


def fetch_timeseries(rise_id: str, 
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch timeseries data from the RISE API for a given location ID.
    
    Queries the /api/result collection endpoint with filters for locationId and itemId,
    and handles pagination to retrieve all available data points.
    
    Args:
        rise_id: Location ID in format 'rise-{location_id}-{record_id}-{item_id}'
                 Example: 'rise-392-2361-502'
        start_date: Optional start date for filtering data (format: YYYY-MM-DD)
        end_date: Optional end date for filtering data (format: YYYY-MM-DD)
        
    Returns:
        pandas DataFrame containing the timeseries data with columns:
            - datetime: Timestamp of the observation
            - value: The measured/modeled result value
            - unit: Unit of measurement (e.g. 'cfs')
            - variable_name: Parameter name (e.g. 'Lake/Reservoir Inflow')
            - timestep: Temporal resolution (e.g. 'daily')
        
    Raises:
        ValueError: If RISE ID format is invalid or API returns an error
        requests.exceptions.RequestException: If API request fails
        
    Example:
        >>> df = fetch_timeseries('rise-392-2361-502')
        >>> df = fetch_timeseries('rise-392-2361-502', 
        ...                       start_date='2020-01-01', 
        ...                       end_date='2020-12-31')
    """
    # Parse the RISE ID
    ids = _parse_rise_id(rise_id)
    location_id = ids['location_id']
    item_id = ids['item_id']
    
    # Construct the API endpoint for the collection
    url = f"{RISE_API_BASE_URL}/result"
    
    # Set up request headers for JSON:API specification
    # Literal brackets in URL are required — the API ignores percent-encoded bracket params
    headers = {'accept': 'application/vnd.api+json'}

    all_rows = []
    # cursor tracks the oldest date seen; each page fetches records before it
    before_cursor = end_date
    # cache parameter metadata keyed by parameterId to avoid redundant lookups
    param_cache: Dict[int, Dict[str, Any]] = {}

    try:
        while True:
            query = f"filter[locationId]={location_id}&filter[itemId]={item_id}"
            if before_cursor:
                query += f"&filter[dateTime][before]={before_cursor}"
            if start_date:
                query += f"&filter[dateTime][after]={start_date}"

            response = requests.get(f"{url}?{query}", headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            records = data.get('data', [])

            if not records:
                break

            for result in records:
                attrs = result.get('attributes', {})
                param_id = attrs.get('parameterId')
                if param_id not in param_cache:
                    param_cache[param_id] = _fetch_parameter_metadata(param_id, headers)
                row = {
                    'datetime': attrs.get('dateTime'),
                    'value': attrs.get('result'),
                    'unit': param_cache[param_id]['parameter_unit'],
                    'variable_name': param_cache[param_id]['parameter_name'],
                    'timestep': param_cache[param_id]['parameter_timestep'],
                }
                all_rows.append(row)

            # Advance cursor to the oldest date on this page (date only, avoids + encoding)
            oldest_dt = records[-1]['attributes'].get('dateTime', '')
            before_cursor = oldest_dt[:10] if oldest_dt else None
            if not before_cursor:
                break
        
        # Create DataFrame and parse datetime column
        if not all_rows:
            return pd.DataFrame(columns=['datetime', 'value', 'unit', 'variable_name', 'timestep'])
        
        df = pd.DataFrame(all_rows)
        
        if 'datetime' in df.columns and not df.empty:
            df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
            df = df.sort_values('datetime').reset_index(drop=True)

        formatted_df = _format_timeseries(df, rise_id)
        
        return formatted_df
        
    except requests.exceptions.HTTPError as e:
        raise ValueError(
            f"Failed to fetch data for {rise_id}. "
            f"API returned status {response.status_code}: {response.text}"
        ) from e
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(
            f"Error connecting to RISE API for {rise_id}: {str(e)}"
        ) from e

def _format_timeseries(df: pd.DataFrame, rise_id: str,
                      constant_field_values: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Format a fetch_timeseries DataFrame into the standard TEEHR-compatible schema.

    Args:
        df: DataFrame returned by fetch_timeseries
        rise_id: RISE ID used to fetch the data; used as location_id
        constant_field_values: Override defaults for constant columns.
            Defaults: reference_time=None, variable_name='streamflow_daily_mean',
            configuration_name='usbr_observations', unit_name='cms'

    Returns:
        DataFrame with columns: reference_time, value_time, value,
        variable_name, configuration_name, unit_name, location_id
    """
    constants = {**_DEFAULT_CONSTANT_FIELDS, **(constant_field_values or {})}

    out = pd.DataFrame()
    # datetimes from the API include +00:00 offset; normalize to UTC-aware regardless
    vt = df['datetime']
    if vt.dt.tz is None:
        vt = vt.dt.tz_localize('UTC', ambiguous='NaT', nonexistent='NaT')
    else:
        vt = vt.dt.tz_convert('UTC')
    out['value_time'] = vt
    out['value'] = df['value'] * _CFS_TO_CMS
    out['location_id'] = rise_id

    for col in ['reference_time', 'variable_name', 'configuration_name', 'unit_name']:
        out[col] = constants[col]

    return out[_OUTPUT_COLUMNS]
