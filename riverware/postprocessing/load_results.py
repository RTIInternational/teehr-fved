"""Push CRMMS results to downstream storage (S3, database, etc.)."""

from pathlib import Path

import pandas as pd


def _coerce_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("reference_time", "value_time"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True).astype("datetime64[us, UTC]")
    return df


def save_parquet(df: pd.DataFrame, parquet_path: Path) -> None:
    parquet_path = Path(parquet_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    _coerce_timestamps(df).to_parquet(parquet_path, index=False)


def run_postprocessing(
    model_dir: Path,
    configuration_name: str,
    parquet_path: Path | None = None,
    location_id_prefix: str = "crmms",
) -> pd.DataFrame:
    """Extract all RDF outputs from model_dir; optionally write Parquet. Returns the DataFrame."""
    from riverware.postprocessing.extract_outputs import extract_rdf_outputs

    model_dir = Path(model_dir)
    df = extract_rdf_outputs(
        rdf_dir=model_dir / "rdfOutput",
        log_path=model_dir / "run.log",
        configuration_name=configuration_name,
        location_id_prefix=location_id_prefix,
    )

    if parquet_path is not None:
        save_parquet(df, parquet_path)

    return df
