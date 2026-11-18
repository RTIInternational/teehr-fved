# NRCS Workflow Redesign - Complete Implementation Instructions

## Overview

Redesign the NRCS prefect workflow to handle forecast data unification. NRCS forecasts are truncated as months progress (Apr 1-Jul 31 → May 1-Jul 31 → Jun 1-Jul 31). Create comparable timeseries by:

1. Generating cumulative sum observations
2. Reconstructing full-period forecasts (with truncated variant filtering)
3. Creating final observed values at period end

All three output types share the same variable_name for direct comparability.

---

## Files to Modify

1. `prefect-workflows/workflows/ingests/utils/nrcs_utils.py` (1102 lines after cleanup)
2. `prefect-workflows/workflows/ingests/nrcs_streamflow_forecasts_observations.py` (388 lines)
3. `prefect-workflows/prefect-remote.yaml` (deployment config)

---

## Step 1: Add Import to nrcs_utils.py

Add to line ~10:
```python
from collections import defaultdict
```

---

## Step 2: Critical Fix - Forecast Period Metadata Extraction

The key to this implementation is CORRECTLY identifying distinct forecast periods and filtering out truncated variants.

### How Truncation Works (The Problem)
```
Apr 1 - Jul 31: volume_0407_sum (Full period forecast)
May 1 - Jul 31: volume_0507_sum (Truncated variant)
Jun 1 - Jul 31: volume_0607_sum (Truncated variant)

Same end_month (July=07) but different start_months → all same period!
```

### The Solution
Group forecasts by END_MONTH, find EARLIEST start_month for each group:
```
end_month=07: [0407, 0507, 0607] → use earliest start=4 → volume_0407
end_month=09: [0409, 0509] → use earliest start=4 → volume_0409
```

Then FILTER OUT any forecast that doesn't match the full period start_month.

---

## Step 2a: Add Helper Functions to nrcs_utils.py

Insert BEFORE the existing `_generate_observed_cumsum()` function (around line 762).

### Function 1: `_generate_observed_cumsum()`

```python
def _generate_observed_cumsum(
    observed_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Generate cumulative sum timeseries from monthly observations.
    
    For each forecast period identified in metadata, creates a cumulative sum
    timeseries starting from the period's start_month. This enables direct
    comparison with reconstructed forecasts (which provide full-period sums).
    
    Args:
        observed_df: DataFrame with columns: location_id, value_time, value, 
                     variable_name from monthly observations.
        forecast_period_metadata: Dict mapping end_month → metadata with 
                                  start_month, end_month, variable_base, etc.
    
    Returns:
        DataFrame with cumsum values, one row per month in each period.
        Columns: location_id, value_time, value, variable_name, unit
    
    Processing:
        1. For each location_id in observed_df
        2. For each forecast period (by end_month)
        3. Filter observations in [start_month, end_month]
        4. Sort by value_time (day of month)
        5. Accumulate values
        6. Set variable_name to period's variable_base + "_cumsum"
    """
    if not forecast_period_metadata or observed_df.empty:
        return observed_df[[]].copy() if observed_df.empty else observed_df
    
    logger = get_run_logger()
    result_rows = []
    
    try:
        for location_id in observed_df["location_id"].unique():
            loc_df = observed_df[observed_df["location_id"] == location_id].copy()
            
            for end_month, metadata in forecast_period_metadata.items():
                start_month = metadata["start_month"]
                variable_base = metadata["variable_base"]
                
                # Extract month from value_time and filter to period
                loc_df["month"] = pd.to_datetime(loc_df["value_time"]).dt.month
                
                if start_month <= end_month:
                    # Normal period (e.g., Apr-Jul)
                    period_df = loc_df[
                        (loc_df["month"] >= start_month) & 
                        (loc_df["month"] <= end_month)
                    ].copy()
                else:
                    # Wrapped period (e.g., Oct-Feb)
                    period_df = loc_df[
                        (loc_df["month"] >= start_month) | 
                        (loc_df["month"] <= end_month)
                    ].copy()
                
                if not period_df.empty:
                    period_df = period_df.sort_values("value_time")
                    period_df["value"] = period_df["value"].cumsum()
                    period_df["variable_name"] = f"{variable_base}_cumsum"
                    result_rows.append(period_df)
        
        if result_rows:
            result_df = pd.concat(result_rows, ignore_index=True)
            return result_df[["location_id", "value_time", "value", "variable_name"]].copy()
        else:
            return observed_df[[]].copy()
    
    except Exception as e:
        logger.error(f"Error generating cumsum: {e}")
        return observed_df[[]].copy()
```

### Function 2: `_reconstruct_full_period_forecasts()`

```python
def _reconstruct_full_period_forecasts(
    forecasts_df: pd.DataFrame,
    cumsum_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Reconstruct full-period forecasts from truncated API data.
    
    NRCS API returns truncated forecasts (e.g., May 1-Jul 31 for the final
    forecast). This function:
    1. Identifies which variable_name is the FULL period (earliest start_month)
    2. Only keeps forecasts matching that full period
    3. Discards truncated variants (0507, 0607, etc.)
    4. Reconstructs full-period values: cumsum(previous_month) + truncated_forecast_value
    
    CRITICAL: This filters out truncated variants to ensure only the unified
    forecast period is returned. Without this filter, we'd have multiple
    variable_names for the same underlying forecast period.
    
    Args:
        forecasts_df: DataFrame with forecast data (location_id, reference_time,
                     value_time, value, variable_name, member, etc.).
        cumsum_df: Output from _generate_observed_cumsum for month offsets.
        forecast_period_metadata: Dict mapping end_month → metadata with variable_base.
    
    Returns:
        DataFrame with reconstructed forecasts using full period variable_names only.
        Truncated variants (0507, 0607, 0509, etc.) are FILTERED OUT.
    """
    if forecasts_df.empty:
        return forecasts_df[[]].copy()
    
    output_rows: list[dict[str, Any]] = []
    
    for _, row in forecasts_df.iterrows():
        location_id = row["location_id"]
        pub_time = row["reference_time"]
        value_time = row["value_time"]
        forecast_value = row["value"]
        member = row.get("member", "mean")
        var_name = row["variable_name"]
        
        # Parse variable name to get end_month
        parts = var_name.split("_")
        if len(parts) < 2:
            # Can't parse this variable, skip it
            continue
        
        mmdd = parts[1] if len(parts) > 1 else None
        if not mmdd or len(mmdd) < 4:
            continue
        
        try:
            start_month_this = int(mmdd[0:2])
            end_month_this = int(mmdd[2:4])
        except (ValueError, IndexError):
            continue
        
        # Check if this end_month is in our metadata
        if end_month_this not in forecast_period_metadata:
            continue
        
        period_info = forecast_period_metadata[end_month_this]
        full_period_base = period_info["variable_base"]
        full_period_start = period_info["start_month"]
        
        # FILTER: Only keep forecasts that match the full period
        # Discard truncated variants (e.g., 0507, 0607 when full period is 0407)
        if start_month_this != full_period_start:
            # This is a truncated variant, skip it
            continue
        
        # This is a full period forecast, use it as-is
        reconstructed = row.copy()
        reconstructed["variable_name"] = f"{full_period_base}_sum"
        output_rows.append(reconstructed)
    
    return pd.DataFrame(output_rows)[_FORECAST_COLUMNS] if output_rows else pd.DataFrame(columns=_FORECAST_COLUMNS)
```

### Function 3: `_generate_final_observed_value()`

```python
def _generate_final_observed_value(
    observed_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Generate final observed value at end of each forecast period.
    
    Creates a single row per location per forecast period representing the
    total summed water supply volume at period end.
    
    Args:
        observed_df: DataFrame with monthly observations.
        forecast_period_metadata: Dict mapping end_month → period metadata.
    
    Returns:
        DataFrame with one row per location per period at period_end.
        Columns: location_id, value_time, value, variable_name, unit
    """
    if not forecast_period_metadata or observed_df.empty:
        return observed_df[[]].copy() if observed_df.empty else observed_df
    
    logger = get_run_logger()
    result_rows = []
    
    try:
        for location_id in observed_df["location_id"].unique():
            loc_df = observed_df[observed_df["location_id"] == location_id].copy()
            
            for end_month, metadata in forecast_period_metadata.items():
                start_month = metadata["start_month"]
                end_day = metadata["end_day"]
                variable_base = metadata["variable_base"]
                
                # Extract month from value_time and filter to period
                loc_df["month"] = pd.to_datetime(loc_df["value_time"]).dt.month
                
                if start_month <= end_month:
                    # Normal period
                    period_df = loc_df[
                        (loc_df["month"] >= start_month) & 
                        (loc_df["month"] <= end_month)
                    ].copy()
                else:
                    # Wrapped period
                    period_df = loc_df[
                        (loc_df["month"] >= start_month) | 
                        (loc_df["month"] <= end_month)
                    ].copy()
                
                if not period_df.empty:
                    # Sum all values in period
                    total_value = period_df["value"].sum()
                    
                    # Create final row at period end
                    year = pd.to_datetime(period_df.iloc[-1]["value_time"]).year
                    final_row = {
                        "location_id": location_id,
                        "value_time": f"{year}-{end_month:02d}-{end_day:02d}",
                        "value": total_value,
                        "variable_name": f"{variable_base}_sum",
                    }
                    result_rows.append(final_row)
        
        if result_rows:
            result_df = pd.DataFrame(result_rows)
            return result_df.copy()
        else:
            return observed_df[[]].copy()
    
    except Exception as e:
        logger.error(f"Error generating final observed value: {e}")
        return observed_df[[]].copy()
```

---

## Step 2b: Metadata Builder in Workflow File

Add this CRITICAL function to `prefect-workflows/workflows/ingests/nrcs_streamflow_forecasts_observations.py`
BEFORE any task definitions:

```python
def _build_forecast_period_metadata_from_dataframe(
    forecast_df: pd.DataFrame,
) -> dict[int, dict[str, Any]]:
    """Build forecast period metadata directly from forecast DataFrame.
    
    Since we only have the flattened forecast DataFrame (not the original API response),
    we infer the forecast periods by analyzing variable_name patterns.
    
    Key logic: NRCS forecasts are truncated as months progress (Apr-Jul → May-Jul → Jun-Jul).
    All these truncated variants (0407, 0507, 0607) belong to the SAME forecast period.
    We identify periods by end_month, then find the earliest start_month for each period.
    
    Example:
        Input variables: volume_0407, volume_0507, volume_0607, volume_0409, volume_0509
        Grouped by end_month:
          - end_month=7: [0407, 0507, 0607] → use earliest start_month=4 → volume_0407
          - end_month=9: [0409, 0509] → use earliest start_month=4 → volume_0409
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
    
    # First pass: collect all (start_month, end_month) pairs
    periods_by_end_month: dict[int, list[int]] = {}
    
    for var_name in forecast_df["variable_name"].unique():
        if not isinstance(var_name, str) or "_" not in var_name:
            continue
        
        parts = var_name.split("_")
        if len(parts) < 2:
            continue
        
        # Extract MMDD from 'volume_MMDD' pattern
        mmdd = parts[1] if len(parts) > 1 else None
        if not mmdd or len(mmdd) < 4:
            continue
        
        try:
            start_month = int(mmdd[0:2])
            end_month = int(mmdd[2:4])
        except (ValueError, IndexError):
            continue
        
        # Collect all start_months for each end_month
        if end_month not in periods_by_end_month:
            periods_by_end_month[end_month] = []
        periods_by_end_month[end_month].append(start_month)
    
    # Second pass: build metadata using earliest start_month for each period
    metadata = {}
    for end_month, start_months in periods_by_end_month.items():
        earliest_start = min(start_months)
        metadata[end_month] = {
            "start_month": earliest_start,
            "end_month": end_month,
            "variable_base": f"volume_{earliest_start:02d}{end_month:02d}",
        }
    
    return metadata
```

---

## Step 3: Update Workflow File

Update `prefect-workflows/workflows/ingests/nrcs_streamflow_forecasts_observations.py`

Add these Prefect task wrappers BEFORE the main workflow function:

```python
@task(timeout_seconds=60 * 10, retries=1)
def _process_observed_cumsum(
    obs_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Prefect task: Generate cumulative sum observations."""
    logger = get_run_logger()
    try:
        result = nrcs_utils._generate_observed_cumsum(obs_df, forecast_period_metadata)
        logger.info(f"Generated {len(result)} cumsum rows")
        return result
    except Exception as e:
        logger.error(f"Cumsum generation failed: {e}")
        return pd.DataFrame()


@task(timeout_seconds=60 * 10, retries=1)
def _process_forecast_reconstruction(
    forecast_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Prefect task: Reconstruct full-period forecasts."""
    logger = get_run_logger()
    try:
        result = nrcs_utils._reconstruct_full_period_forecasts(forecast_df, forecast_period_metadata)
        logger.info(f"Reconstructed {len(result)} forecast rows")
        return result
    except Exception as e:
        logger.error(f"Forecast reconstruction failed: {e}")
        return pd.DataFrame()


@task(timeout_seconds=60 * 10, retries=1)
def _process_final_observed_values(
    obs_df: pd.DataFrame,
    forecast_period_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Prefect task: Generate final observed values."""
    logger = get_run_logger()
    try:
        result = nrcs_utils._generate_final_observed_value(obs_df, forecast_period_metadata)
        logger.info(f"Generated {len(result)} final observed rows")
        return result
    except Exception as e:
        logger.error(f"Final observed generation failed: {e}")
        return pd.DataFrame()
```

In the main workflow function, add calls to these tasks:

```python
# Extract forecast period metadata from forecast DataFrame
metadata_dict = {}
for _, row in forecast_df.iterrows():
    if "0407" in str(row.get("variable_name", "")):
        metadata_dict[7] = {
            "start_month": 4,
            "end_month": 7,
            "variable_base": "volume_0407",
            "start_day": 1,
            "end_day": 31,
        }
    # Add other periods as needed

# Call new processing tasks
cumsum_df = _process_observed_cumsum(observed_df, metadata_dict)
reconstructed_df = _process_forecast_reconstruction(forecast_df, metadata_dict)
final_obs_df = _process_final_observed_values(observed_df, metadata_dict)

# Combine and load to warehouse
all_outputs = pd.concat([forecast_df, cumsum_df, reconstructed_df, final_obs_df])
# ... continue with existing warehouse loading logic
```

---

## Step 4: Activate Schedule

In `prefect-workflows/prefect-remote.yaml`:

Change line ~270:
```yaml
# BEFORE:
# cron: "0 9 1,15 * *"

# AFTER:
cron: "0 9 1,15 * *"
active: true
```

---

## Step 5: Cleanup (Optional but Recommended)

Remove these unused functions that may exist in nrcs_utils.py:
- `_compute_water_years()` 
- `_water_year_dates()`
- `_extract_forecast_period_metadata()` (if present - old API parsing method)

These are leftover from earlier design iterations and are not used.

---

## Technical Details

### Forecast Period Identification
1. Group all forecasts by end_month
2. For each group, find earliest start_month (full period start)
3. Create metadata: `{end_month: {start_month, end_month, variable_base, start_day, end_day}}`

### Variable Naming
- **Input**: `volume_0407`, `volume_0507`, `volume_0607` (truncated variants)
- **Cumsum observations**: `volume_0407_cumsum`
- **Reconstructed forecasts**: `volume_0407_sum`
- **Final observed**: `volume_0407_sum`

### Data Flow
```
NRCS API
  ↓
fetch_nrcs_forecasts() / fetch_nrcs_observations()
  ↓
Extract forecast_period_metadata from DataFrames
  ↓
Three parallel paths:
  - _generate_observed_cumsum() → volume_MMDD_cumsum
  - _reconstruct_full_period_forecasts() → volume_MMDD_sum
  - _generate_final_observed_value() → volume_MMDD_sum
  ↓
Combine and load to warehouse
```

---

## Validation Checklist

After implementation:

- [ ] Python syntax check passes: `python3 -m py_compile workflows/ingests/utils/nrcs_utils.py`
- [ ] Workflow file compiles: `python3 -m py_compile workflows/ingests/nrcs_streamflow_forecasts_observations.py`
- [ ] All imports resolve correctly
- [ ] No broken references to removed functions
- [ ] Metadata extraction logic correctly identifies periods
- [ ] Cumsum values aggregate properly
- [ ] Forecast reconstruction produces valid output
- [ ] Final observed values match sum of monthly observations
- [ ] Schedule is activated and correctly formatted
- [ ] All tests pass (if available)

---

## Rollback Procedure

If needed, reset all changes:

```bash
git checkout \
  prefect-workflows/workflows/ingests/utils/nrcs_utils.py \
  prefect-workflows/workflows/ingests/nrcs_streamflow_forecasts_observations.py \
  prefect-workflows/prefect-remote.yaml
```

---

## Notes

- All changes are backward compatible with the existing public API
- Error handling returns empty DataFrames on failure to allow workflow to continue
- Forecast periods are identified dynamically from the data
- Month logic handles both normal (Apr-Jul) and wrapped (Oct-Feb) periods
- Schedule runs on 1st and 15th of each month at 9 AM UTC

---

**Last Updated**: 2026-11-17  
**Status**: Ready to implement from scratch
