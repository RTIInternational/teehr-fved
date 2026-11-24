# CBRFC Seasonal Water Supply Forecast Workflow

## Overview

This workflow ingests CBRFC (Colorado Basin River Forecast Center) seasonal water supply forecasts and observations for specified water years and locations. Data is fetched from CBRFC's public API, processed according to TEEHR schema requirements, and written to the warehouse using `upsert` mode to handle daily runs querying full water years.

## Workflow Parameters

### Required Parameters

- **`end_WY`** (int): The ending water year to fetch. For example, `2026` will fetch water year 2026 (Oct 1, 2025 - Sept 30, 2026).

### Optional Parameters

- **`start_WY`** (int, optional): The starting water year. If not specified, defaults to `end_WY` (single year fetch). To fetch multiple years, specify both `start_WY` and `end_WY`. For example, `start_WY=2023, end_WY=2026` will fetch all four water years.

- **`location_ids`** (list[str], optional): List of specific location IDs to fetch (e.g., `['cbrfc-OAWU1', 'cbrfc-GRNU1']`). If not specified, all 14 CBRFC locations are fetched by default.

- **`temp_dir_path`** (str): Path to temporary directory for intermediate parquet files. Default: `/data/temp-spark`

- **`start_spark_cluster`** (bool): Whether to start a Spark cluster for processing. Default: `False`

## Water Year Definition

A water year (WY) is defined as October 1 through September 30 of the following calendar year:

- **WY 2026** = October 1, 2025 - September 30, 2026
- **WY 2025** = October 1, 2024 - September 30, 2025
- **WY 2024** = October 1, 2023 - September 30, 2024

## Data Variables and Naming Conventions

### Forecast Data

Forecast data uses the naming convention `volume_XXXX_sum` where `XXXX` represents the start and end months of the aggregation period:

| Variable Name | Forecast Period | Start Month | End Month |
|---|---|---|---|
| `volume_0407_sum` | April - July | 4 | 7 |
| `volume_0106_sum` | January - June | 1 | 6 |
| `volume_0105_sum` | January - May | 1 | 5 |

Forecast data includes ensemble members (max, p90, p70, p50, p30, p10, min, crx, c70, cmp, c30, crn).

### Observation Data (Cumulative Sum Timeseries)

Observation data is tagged with the cumsum naming convention `volume_XXXX_cumsum` to indicate that the values represent cumulative sums over the forecast period:

| Variable Name | Corresponds to Forecast | Description |
|---|---|---|
| `volume_0407_cumsum` | `volume_0407_sum` | Cumulative observed runoff (Apr-Jul) |
| `volume_0106_cumsum` | `volume_0106_sum` | Cumulative observed runoff (Jan-Jun) |
| `volume_0105_cumsum` | `volume_0105_sum` | Cumulative observed runoff (Jan-May) |

### Final Observed Timeseries

A "final observed" timeseries is created for each location using the **forecast variable name** (e.g., `volume_0407_sum`, not cumsum). This contains a single value: the last reported cumulative sum value from the observation timeseries. This is used for metric calculations where forecast and observation data must have matching `variable_name` values.

**Value Time**: Set to the start date of the forecast period (e.g., April 1, 2025 for April-July forecasts)

**Conditions**: Only created after the forecast period has ended

## Configurations

Two configurations are created/used in the warehouse:

1. **`cbrfc_unregulated_official_forecast`** (secondary_timeseries)
   - Forecast ensemble data
   - Type: secondary

2. **`cbrfc_unregulated_observed`** (primary_timeseries)
   - Observation data (both cumsum timeseries and final observed single values)
   - Type: primary

## Data Flow

```
┌─────────────────────────────────┐
│ Input Parameters                 │
│ - end_WY (required)             │
│ - start_WY (optional)           │
│ - location_ids (optional)       │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Fetch CBRFC Data                 │
│ For each water year:             │
│ - Query CBRFC API per location  │
│ - Parse CSV response             │
│ - Convert KAF to m³             │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Process Data                     │
│ - Rename obs: _sum → _cumsum    │
│ - Create final observed (1 row) │
│ - Filter unmapped variables     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Combine Multi-Year Results       │
│ - Concat sim_df across years    │
│ - Concat obs_df across years    │
│ - Concat final_obs_df           │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Write to Warehouse               │
│ - secondary_timeseries (upsert) │
│ - primary_timeseries (upsert)   │
└─────────────────────────────────┘
```

## Usage Examples

### Single Year, All Locations

```bash
# Fetch WY 2025 for all 14 CBRFC locations
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/my-deployment \
  --param end_WY=2025
```

### Multiple Years, All Locations

```bash
# Fetch WY 2023, 2024, 2025 for all locations
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/my-deployment \
  --param end_WY=2025 \
  --param start_WY=2023
```

### Single Year, Specific Locations

```bash
# Fetch WY 2025 for two specific locations
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/my-deployment \
  --param end_WY=2025 \
  --param location_ids='["cbrfc-OAWU1", "cbrfc-GRNU1"]'
```

### Multi-Year, Specific Locations

```bash
# Fetch WY 2023-2025 for specific locations
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/my-deployment \
  --param end_WY=2025 \
  --param start_WY=2023 \
  --param location_ids='["cbrfc-OAWU1", "cbrfc-GRNU1", "cbrfc-GRNU1"]'
```

## Supported CBRFC Locations

The workflow supports the following 14 CBRFC locations:

```
cbrfc-DIRC2  cbrfc-DLAC2  cbrfc-DRGC2  cbrfc-GBRW4
cbrfc-GJNC2  cbrfc-GLDA3  cbrfc-GRNU1  cbrfc-MBLC2
cbrfc-NVRN5  cbrfc-OAWU1  cbrfc-RURC2  cbrfc-TPIC2
cbrfc-VIRU1  cbrfc-YDLC2
```

## Scheduling

### Local Testing (`prefect-local.yaml`)

- **Schedule**: None (manual testing only)
- **Concurrency**: No limit
- **Resource Tier**: Kubernetes pool (testing configuration)

### Production (`prefect-remote.yaml`)

- **Schedule**: Daily at 6:00 AM UTC (`0 6 * * *`)
- **Active**: Yes (enabled by default)
- **Concurrency**: Limited to 1 (prevents parallel runs)
- **Resource Tier**: Medium (2 CPU, 20Gi memory)
- **Tags**: `[k8s, cbrfc]`

## Implementation Details

### Module Structure

- **`workflows/ingests/cbrfc_seasonal_wsv_forecast.py`**: Main workflow implementation
  - Core flow orchestration
  - Parameter validation
  - Multi-year looping logic
  - Warehouse write operations

- **`workflows/ingests/utils/cbrfc_seasonal_utils.py`**: Supporting utilities
  - CBRFC API interaction
  - Data parsing and formatting
  - Variable renaming functions
  - Final observed timeseries generation
  - Water year calculation utilities

### Key Functions

#### Water Year Utilities
- `water_year_to_dates(water_year)`: Convert WY to date range
- `get_water_year_from_date(date)`: Determine WY for a given date
- `is_water_year_valid(water_year)`: Validate WY parameter

#### Data Fetching
- `fetch_seasonal_wsup_forecasts(location_ids, year)`: Fetch data for given locations and water year

#### Data Processing
- `rename_observed_variables(obs_df)`: Rename obs from _sum to _cumsum
- `create_final_observed_timeseries(obs_df, ...)`: Generate final observed single-value timeseries

### Error Handling

The workflow implements graceful error handling:

1. **Parameter Validation**: Water years are validated before processing starts
2. **Location-Level Errors**: If a location fetch fails, that location is skipped and other locations continue processing
3. **Empty Data**: Empty dataframes are handled gracefully at all processing stages
4. **Variable Filtering**: Unknown/unmapped variables are filtered out with warnings

### Write Mode: Upsert

The workflow uses `write_mode='upsert'` for both forecast and observation data. This means:

- **New records**: Inserted into the warehouse
- **Existing records**: Updated if data has changed
- **Identifier fields**: The warehouse uses reference_time + value_time + location_id + variable_name to identify duplicate records

This is important because:
- The workflow runs daily but queries full water years
- Forecast data is periodically updated/reissued by CBRFC
- Using upsert ensures we capture the latest forecast values

## Troubleshooting

### Common Issues

**Issue**: "Could not fetch CBRFC seasonal forecast from..."
- **Cause**: Network connectivity issue or CBRFC API is unavailable
- **Solution**: Check internet connectivity; CBRFC server status; verify location ID format

**Issue**: "Unsupported CBRFC seasonal aggregation period"
- **Cause**: CBRFC returned a forecast period not in SEASONAL_PERIODS mapping
- **Solution**: This is a code issue. Contact development to add new forecast period support.

**Issue**: "The following variables were not found in CBRFC_SEASONAL_VARIABLE_MAPPING"
- **Cause**: CBRFC returned forecast ensemble member names that aren't in RAW_KEYS_TO_TEEHR_VARIABLES
- **Solution**: This is rare; check CBRFC API changes; may need code update

### Debugging

Enable debug logging by setting environment variable:
```bash
export PREFECT_LOGGING_LEVEL=DEBUG
```

Check Prefect logs:
```bash
prefect deployment logs ingest-cbrfc-seasonal-wsv-forecasts/my-deployment --follow
```

## Performance Considerations

- **Data Volume**: ~1600 forecast rows per location per year; ~120 observation rows per location per year
- **Processing Time**: ~30-60 seconds per water year for all 14 locations
- **Network I/O**: One CBRFC API request per location per year (14 requests for single-year full ingest)
- **Timeout**: Default 30 seconds per location request; adjust if network is slow

## Future Enhancements

1. **Dynamic Location Discovery**: Read location list from warehouse configuration instead of hardcoding
2. **Incremental Updates**: Only fetch data since last successful run instead of full water year
3. **Parallel Location Fetching**: Use Prefect task mapping to fetch multiple locations in parallel
4. **Additional Forecast Periods**: Support for January-June and January-May periods when available
5. **Backfill Support**: Command-line tool to easily backfill historical years

## References

- CBRFC Seasonal Water Supply Forecasts: https://www.cbrfc.noaa.gov/wsup/
- TEEHR Documentation: https://github.com/NOAA-OWP/teehr
- Water Year Definition: https://en.wikipedia.org/wiki/Water_year

## Contacts

For questions or issues with this workflow, contact:
- Workflow Development: [contact info]
- CBRFC Data Issues: [contact info]
