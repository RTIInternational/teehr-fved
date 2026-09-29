"""Parse RiverWare output files (CSV, RDF, etc.)."""

from pathlib import Path

import pandas as pd

from riverware.utils.riverware_utils import parse_rdf, parse_reference_time_from_log

# Preferred TEEHR variable names for common CRMMS slots ({type}_{timestep}_{aggregation}).
# Slots not listed here fall back to snake_case of the RiverWare slot name.
CRMMS_VARIABLE_MAP: dict[str, str] = {
    # Reservoir state (end-of-period)
    "Pool Elevation":              "poolelevation_monthly_inst",
    "Storage":                     "storage_monthly_inst",
    # "Surface Area":                "surface_area_monthly_inst",
    # "Bank Storage":                "bank_storage_monthly_inst",
    # Flows / volumes (mean flow rates)
    "Inflow":                      "inflow_monthly_mean",
    "Local Inflow":                "localinflow_monthly_mean",
    "Outflow":                     "outflow_monthly_mean",
    "Turbine Release":             "turbinerelease_monthly_mean",
    "Regulated Spill":             "regulatedspill_monthly_mean",
    "Unregulated Spill":           "unregulatedspill_monthly_mean",
    "Unregulated":                 "unregulatedinflow_monthly_mean",
    "Bypass":                      "bypass_monthly_mean",
    # "Evaporation":                 "evaporation_monthly_inst",
    # "Peak Flow":                   "peak_flow_monthly_total",
    # # Diversions
    # "Diversion":                   "diversion_monthly_sum",
    # "Diversion Requested":         "diversion_requested_monthly_total",
    # "Total Diversion":             "diversion_monthly_sum",
    # "Total Diversion Requested":   "total_diversion_requested_monthly_total",
    # # Energy / operations
    "Energy":                      "energy_monthly_sum",
    # "Peak Hours":                  "peak_hours_monthly_total",
    # # Flags / dimensionless indicators
    # "Shortage Flag":               "shortage_flag_monthly",
    # "Flood Control Flag":          "flood_control_flag_monthly",
    # "Flood Control Surplus Flag":  "flood_control_surplus_flag_monthly",
    # "Power Plant Cap Fraction":    "power_plant_cap_fraction_monthly",
}

ACRE_FT_TO_M3 = 1233.48183754752
FT_TO_M = 0.3048
CFS_TO_CMS = FT_TO_M ** 3

# RiverWare unit -> (TEEHR unit, conversion factor). "acre-ft/month" is handled separately.
UNIT_CONVERSIONS: dict[str, tuple[str, float]] = {
    "acre-ft": ("m^3", ACRE_FT_TO_M3),
    "cfs":     ("m^3/s", CFS_TO_CMS),
    "ft":      ("m", FT_TO_M),
}


def convert_to_metric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert RiverWare English units to TEEHR metric units in place of the originals.

    Monthly volumes (acre-ft/month) become mean flow in m^3/s over the month.
    Raises ValueError on any unit without a known conversion.
    """
    df = df.copy()

    monthly = df["unit_name"] == "acre-ft/month"
    # value_time is the end-of-period instant, so the month covered ends the day before.
    seconds = (df.loc[monthly, "value_time"] - pd.Timedelta(days=1)).dt.days_in_month * 86400
    df.loc[monthly, "value"] = df.loc[monthly, "value"] * ACRE_FT_TO_M3 / seconds
    df.loc[monthly, "unit_name"] = "m^3/s"

    for unit, (metric_unit, factor) in UNIT_CONVERSIONS.items():
        mask = df["unit_name"] == unit
        df.loc[mask, "value"] = df.loc[mask, "value"] * factor
        df.loc[mask, "unit_name"] = metric_unit

    unknown = set(df["unit_name"].unique()) - {"m^3/s", "m^3", "m", "GWH"}
    if unknown:
        raise ValueError(f"No metric conversion defined for units: {sorted(unknown)}")
    return df


def check_no_nans(df: pd.DataFrame) -> None:
    """Raise ValueError listing where NaN values occur, since TEEHR validation rejects them."""
    nan_rows = df[df["value"].isna()]
    if nan_rows.empty:
        return
    summary = (
        nan_rows.groupby(["location_id", "variable_name"])
        .agg(
            count=("value", "size"),
            first_time=("value_time", "min"),
            last_time=("value_time", "max"),
            members=("member", "nunique"),
        )
    )
    raise ValueError(
        f"{len(nan_rows):,} NaN values found in {len(df):,} rows:\n{summary.to_string()}"
    )


def extract_rdf_outputs(
    rdf_dir: Path,
    log_path: Path,
    configuration_name: str,
    location_id_prefix: str = "crmms",
    variable_name_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Read all RDF files in rdf_dir and return a TEEHR secondary_timeseries DataFrame.

    Only slots present in CRMMS_VARIABLE_MAP (or variable_name_map overrides) are included.
    Unmapped slots are silently skipped.
    """
    rdf_dir = Path(rdf_dir)
    log_path = Path(log_path)

    reference_time = parse_reference_time_from_log(log_path)
    effective_map = {**CRMMS_VARIABLE_MAP, **(variable_name_map or {})}

    records: list[dict] = []
    for rdf_file in sorted(rdf_dir.glob("*.rdf")):
        for rec in parse_rdf(rdf_file):
            variable_name = effective_map.get(rec["slot_name"])
            if variable_name is None:
                continue
            records.append(
                {
                    "reference_time": reference_time,
                    "value_time": rec["value_time"],
                    "configuration_name": configuration_name,
                    "unit_name": rec["unit_name"],
                    "variable_name": variable_name,
                    "value": rec["value"],
                    "location_id": f"{location_id_prefix}-{rec['object_name']}",
                    "member": str(rec["trace"]),
                }
            )

    df = pd.DataFrame(
        records,
        columns=[
            "reference_time",
            "value_time",
            "configuration_name",
            "unit_name",
            "variable_name",
            "value",
            "location_id",
            "member",
        ],
    )
    df["reference_time"] = pd.to_datetime(df["reference_time"], utc=True)
    df["value_time"] = pd.to_datetime(df["value_time"], utc=True)
    check_no_nans(df)
    return convert_to_metric(df)
