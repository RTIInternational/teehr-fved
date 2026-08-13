"""Parse RiverWare output files (CSV, RDF, etc.)."""

import re
from pathlib import Path

import pandas as pd

from riverware.utils.riverware_utils import parse_rdf, parse_reference_time_from_log

# Preferred TEEHR variable names for common CRMMS slots ({type}_{timestep}_{aggregation}).
# Slots not listed here fall back to snake_case of the RiverWare slot name.
CRMMS_VARIABLE_MAP: dict[str, str] = {
    # Reservoir state (end-of-period)
    "Pool Elevation":              "pool_elevation_monthly_eop",
    "Storage":                     "storage_monthly_eop",
    "Surface Area":                "surface_area_monthly_eop",
    "Bank Storage":                "bank_storage_monthly_eop",
    # Flows / volumes (monthly total)
    "Inflow":                      "inflow_monthly_total",
    "Local Inflow":                "local_inflow_monthly_total",
    "Outflow":                     "outflow_monthly_total",
    "Turbine Release":             "turbine_release_monthly_total",
    "Regulated Spill":             "regulated_spill_monthly_total",
    "Unregulated Spill":           "unregulated_spill_monthly_total",
    "Unregulated":                 "unregulated_inflow_monthly_total",
    "Bypass":                      "bypass_monthly_total",
    "Evaporation":                 "evaporation_monthly_total",
    "Peak Flow":                   "peak_flow_monthly_total",
    # Diversions
    "Diversion":                   "diversion_monthly_total",
    "Diversion Requested":         "diversion_requested_monthly_total",
    "Total Diversion":             "total_diversion_monthly_total",
    "Total Diversion Requested":   "total_diversion_requested_monthly_total",
    # Energy / operations
    "Energy":                      "energy_monthly_total",
    "Peak Hours":                  "peak_hours_monthly_total",
    # Flags / dimensionless indicators
    "Shortage Flag":               "shortage_flag_monthly",
    "Flood Control Flag":          "flood_control_flag_monthly",
    "Flood Control Surplus Flag":  "flood_control_surplus_flag_monthly",
    "Power Plant Cap Fraction":    "power_plant_cap_fraction_monthly",
}

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")


def _slot_to_variable_name(slot_name: str, extra_map: dict[str, str] | None) -> str:
    """Map a RiverWare slot name to a TEEHR variable name.

    Checks extra_map first, then CRMMS_VARIABLE_MAP, then falls back to snake_case.
    """
    if extra_map and slot_name in extra_map:
        return extra_map[slot_name]
    if slot_name in CRMMS_VARIABLE_MAP:
        return CRMMS_VARIABLE_MAP[slot_name]
    # Fallback: CamelCase + spaces → snake_case
    s = re.sub(r"[\s\-]+", "_", slot_name)
    s = _CAMEL_RE.sub(r"_\1", s)
    return re.sub(r"_+", "_", s).lower().strip("_")


def extract_rdf_outputs(
    rdf_dir: Path,
    log_path: Path,
    configuration_name: str,
    location_id_prefix: str = "crmms",
    variable_name_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Read all RDF files in rdf_dir and return a TEEHR secondary_timeseries DataFrame.

    variable_name_map: optional slot-name → variable-name overrides applied on top of
    CRMMS_VARIABLE_MAP. Unmapped slots fall back to snake_case of the slot name.
    """
    rdf_dir = Path(rdf_dir)
    log_path = Path(log_path)

    reference_time = parse_reference_time_from_log(log_path)

    records: list[dict] = []
    for rdf_file in sorted(rdf_dir.glob("*.rdf")):
        for rec in parse_rdf(rdf_file):
            records.append(
                {
                    "reference_time": reference_time,
                    "value_time": rec["value_time"],
                    "configuration_name": configuration_name,
                    "unit_name": rec["unit_name"],
                    "variable_name": _slot_to_variable_name(rec["slot_name"], variable_name_map),
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
    return df
