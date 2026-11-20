"""Common output schema shared by the three inference packages."""

from __future__ import annotations

import pandas as pd

from .paths import MODEL_VERSION

COLUMNS = ["site_id", "issue_date", "volume_10", "volume_50", "volume_90", "model_version"]


def to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=[c for c in COLUMNS if c != "model_version"])
    df["model_version"] = MODEL_VERSION
    return df[COLUMNS].sort_values(["site_id", "issue_date"]).reset_index(drop=True)


def validate(df: pd.DataFrame) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems = []
    if df.duplicated(["site_id", "issue_date"]).any():
        problems.append("duplicate (site_id, issue_date) rows")
    q = df[["volume_10", "volume_50", "volume_90"]]
    if q.isna().any().any():
        problems.append("NaN quantiles")
    if (q < 0).any().any():
        problems.append("negative quantiles")
    if ((df.volume_10 > df.volume_50) | (df.volume_50 > df.volume_90)).any():
        problems.append("quantiles not ordered")
    return problems
