"""Parse RiverWare output files (CSV, RDF, etc.)."""

from pathlib import Path

import pandas as pd

from riverware.utils.riverware_utils import parse_rdf, parse_reference_time_from_log


def extract_rdf_outputs(
    rdf_dir: Path,
    log_path: Path,
    configuration_name: str,
    location_id_prefix: str = "crmms",
) -> pd.DataFrame:
    """Read all RDF files in rdf_dir and return a TEEHR secondary_timeseries DataFrame."""
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
                    "variable_name": rec["slot_name"],
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
