# CBRFC Seasonal WSV Forecast Workflow - Operator Runbook

## Quick Start

### View Workflow Status
```bash
prefect deployment ls | grep cbrfc-seasonal
prefect flow run ingest-cbrfc-seasonal-wsv-forecasts --show-flow-logs
```

### Manual Trigger (Local Testing)
```bash
cd /home/slandsteiner/repos/teehr-fved/prefect-workflows
prefect flow run workflows/ingests/cbrfc_seasonal_wsv_forecast.py:ingest_cbrfc_seasonal_wsv_forecasts \
  --param temp_dir_path=/data/temp-spark \
  --param end_WY=2025
```

### Manual Trigger (Remote/Production)
```bash
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/default \
  --param end_WY=2026
```

## Operational Tasks

### Running Current Water Year
```bash
# Fetch data for current calendar year (which is part of two water years)
# Example: If today is 2026-11-24, we're in WY 2027 (Oct 2026 - Sept 2027)
# and WY 2026 is complete

prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/default \
  --param end_WY=2027
```

### Backfilling Historical Data
```bash
# Backfill 3 previous water years
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/default \
  --param end_WY=2026 \
  --param start_WY=2024
```

### Testing Single Location
```bash
# Test with a single location before running full ingest
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/default \
  --param end_WY=2025 \
  --param location_ids='["cbrfc-OAWU1"]'
```

### Verifying Data in Warehouse

```python
# Connect to warehouse and check results
from teehr import Evaluation
ev = Evaluation('/path/to/warehouse')

# Check forecast data
sim_df = ev.fetch.timeseries(
    configuration_names=['cbrfc_unregulated_official_forecast'],
    variable_names=['volume_0407_sum']
)
print(f"Forecast rows: {len(sim_df)}")
print(f"Date range: {sim_df['reference_time'].min()} to {sim_df['reference_time'].max()}")

# Check observation data
obs_df = ev.fetch.timeseries(
    configuration_names=['cbrfc_unregulated_observed'],
    variable_names=['volume_0407_cumsum']
)
print(f"Observation rows: {len(obs_df)}")
```

## Monitoring and Debugging

### View Workflow Logs

```bash
# Real-time logs
prefect deployment logs ingest-cbrfc-seasonal-wsv-forecasts/default --follow

# View recent runs
prefect flow run ls | grep cbrfc-seasonal

# Get specific run details
prefect flow-run get <flow-run-id>
```

### Common Log Messages

**Expected Success Indicators:**
```
✅ Fetch successful!
✓ Fetched XXXX forecast rows and XXXX observation rows
✓ Renamed observed variables to cumsum naming
✓ Forecast data written to warehouse
✓ Observation (cumsum) data written to warehouse
✅ CBRFC Seasonal Water Supply Forecast Ingestion Complete
```

**Expected Warnings:**
```
⚠ The following variables were not found in CBRFC_SEASONAL_VARIABLE_MAPPING
  and will be filtered out: ...
```

(This is normal if CBRFC returns unexpected variables)

### Troubleshooting Guide

#### Issue: Workflow times out

**Symptoms:**
```
TimeoutError: Workflow did not complete within timeout_seconds
```

**Causes & Solutions:**
1. **Network is slow**: Increase timeout in workflow code (currently 30s per request)
2. **CBRFC API is slow**: Try running again later; check CBRFC server status
3. **Warehouse is overloaded**: Check warehouse load; try during off-peak hours
4. **Too many locations**: Reduce location_ids list or fetch fewer water years

**Action:**
```bash
# Monitor network connectivity
ping www.cbrfc.noaa.gov

# Check CBRFC API directly
curl "https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py?id=OAWU1&year=2025&db=&csv=1" -v

# Increase timeout for next run (edit workflow code)
# In cbrfc_seasonal_wsv_forecast.py, change timeout parameter
```

#### Issue: "Could not fetch CBRFC seasonal forecast from..." error

**Symptoms:**
```
RuntimeError: Could not fetch CBRFC seasonal forecast from 
https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py?id=... : ...
```

**Causes & Solutions:**
1. **Network connectivity issue**
   - Check internet connectivity: `ping 1.1.1.1`
   - Check CBRFC is reachable: `curl -I https://www.cbrfc.noaa.gov`

2. **Invalid location ID**
   - Verify location IDs start with `cbrfc-` (e.g., `cbrfc-OAWU1`)
   - Check location exists in supported list (14 total locations)

3. **CBRFC API rate limiting**
   - Don't run multiple workflows in parallel
   - Add delay between location fetches (increase in code if needed)

4. **Water year data not available**
   - Some years may not have data
   - Check CBRFC website directly for year availability

**Action:**
```bash
# Test CBRFC connectivity
curl "https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py?id=OAWU1&year=2025&db=&csv=1" | head -20

# If error persists, check individual locations
for loc in DIRC2 DLAC2 DRGC2 GBRW4; do
  echo "Testing $loc..."
  curl -s "https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py?id=$loc&year=2025&db=&csv=1" | head -5
done
```

#### Issue: "Unsupported CBRFC seasonal aggregation period" error

**Symptoms:**
```
ValueError: Unsupported CBRFC seasonal aggregation period: ...
```

**Causes & Solutions:**
1. **CBRFC API changed**: New forecast period not in code
2. **Location returns different period**: Some locations may return different periods

**Action:**
- Contact development team
- May need to update SEASONAL_PERIODS in cbrfc_seasonal_utils.py
- Temporarily exclude affected location(s)

#### Issue: Data not appearing in warehouse

**Symptoms:**
- Workflow completes successfully but no data in warehouse
- Logs show "✅" but query returns no results

**Causes & Solutions:**
1. **Upsert mode issue**: Check warehouse upsert implementation
2. **Wrong table/configuration**: Verify data went to correct table
3. **Data filtering**: Check if all data was filtered out

**Action:**
```bash
# Check if data was written to temp parquet files
ls -la /data/temp-spark/cbrfc_*/

# Manually check temp data
python3 -c "
import pandas as pd
df = pd.read_parquet('/data/temp-spark/cbrfc_forecast/data.parquet')
print(f'Rows: {len(df)}')
print(f'Columns: {df.columns.tolist()}')
print(f'Variables: {df[\"variable_name\"].unique()}')
"

# Check warehouse tables
from teehr import Evaluation
ev = Evaluation('/path/to/warehouse')
configs = ev.fetch.list_configurations()
print(configs)
```

#### Issue: Performance is degraded

**Symptoms:**
- Workflow takes much longer than expected
- CPU/memory usage very high

**Solutions:**
1. **Reduce scope**: Fetch fewer locations or water years
2. **Check warehouse load**: May be processing other workflows
3. **Monitor network**: CBRFC API may be slow
4. **Reduce Spark resources**: Adjust shuffle partitions (currently 4)

**Action:**
```bash
# Monitor while running
watch -n 1 'kubectl top pods -n teehr | grep cbrfc'

# Check warehouse status
# (depends on your warehouse setup)
```

## Preventive Maintenance

### Daily Checks

1. **Verify last successful run**
   ```bash
   prefect flow run ls | grep cbrfc | head -5
   ```

2. **Check for warnings**
   ```bash
   prefect deployment logs ingest-cbrfc-seasonal-wsv-forecasts/default | grep -E "⚠|ERROR" | tail -20
   ```

3. **Spot-check data**
   ```python
   from teehr import Evaluation
   ev = Evaluation('/path/to/warehouse')
   counts = ev.fetch.timeseries(
       configuration_names=['cbrfc_unregulated_official_forecast']
   )
   print(f"Latest forecast count: {len(counts)}")
   ```

### Weekly Tasks

1. **Review schedule compliance**
   - Check that workflow ran at scheduled time
   - Look for delayed starts or failures

2. **Data quality review**
   - Sample locations for data reasonableness
   - Check for unexpected variable names
   - Verify value ranges are realistic

3. **Resource monitoring**
   - Check CPU/memory usage stayed within allocated
   - Look for anomalies or unexpected patterns

### Monthly Tasks

1. **Update documentation** if any changes made
2. **Review parameter defaults** in prefect-remote.yaml
3. **Archive logs** if necessary
4. **Capacity planning** based on data growth

## Emergency Procedures

### Kill a Running Workflow

```bash
# Cancel an in-progress run
prefect flow-run cancel <flow-run-id>

# Or stop all runs of this workflow
prefect flow ls | grep cbrfc-seasonal | xargs prefect flow-run ls --filter "flow_name='$0'" | head -1 | xargs prefect flow-run cancel
```

### Disable Automatic Scheduling

```bash
# Temporarily disable schedule in prefect-remote.yaml
# Change: active: true
# To:     active: false

# Then redeploy:
prefect deployment apply prefect-remote.yaml
```

### Manual Data Repair

If data needs to be corrected/rewritten:

```bash
# Delete corrupted data from warehouse
# (This depends on your warehouse implementation)

# Re-run workflow for affected water year(s)
prefect deployment run ingest-cbrfc-seasonal-wsv-forecasts/default \
  --param end_WY=2025 \
  --param start_WY=2025
```

### Escalation Path

If issues persist:
1. Check CBRFC website status: https://www.cbrfc.noaa.gov/
2. Review recent code changes
3. Contact development team with:
   - Full error message/logs
   - Parameters used
   - Last successful run details
   - Current warehouse status

## References

- Workflow Documentation: [CBRFC_SEASONAL_WORKFLOW.md](./CBRFC_SEASONAL_WORKFLOW.md)
- Prefect Documentation: https://docs.prefect.io/
- CBRFC Data Portal: https://www.cbrfc.noaa.gov/wsup/
- TEEHR Docs: https://github.com/NOAA-OWP/teehr

## Checklist for On-Call Support

When supporting this workflow, verify:

- [ ] Network connectivity to CBRFC server
- [ ] Warehouse is accessible and responsive
- [ ] Spark cluster is running (if start_spark_cluster=true)
- [ ] Enough disk space for temp files (/data/temp-spark/)
- [ ] Prefect agent is running
- [ ] No other CBRFC workflows running (concurrency limit=1)
- [ ] CBRFC API not rate-limiting
- [ ] Location IDs are valid and formatted correctly
- [ ] Water year parameters are within valid range
