"""Competition-style interface over the live-stage `solution.py` (built into <root>/build/src, patched by patches/*.patch).

    preprocess(src_dir, data_dir, preprocessed_dir) -> assets
    predict(site_id, issue_date, assets, src_dir, data_dir, preprocessed_dir) -> (q10, q50, q90)   # KAF
    run_forecast(paths, issue_date, sites=None) -> (forecasts DataFrame, errors list, warnings list)

The live code generates features for the whole January-July grid of the issue year in one call and returns every grid
date up to the issue date; `run_forecast` keeps only the issue date. Features for a row only use data before its date.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from . import schema
from .paths import Paths

_LIVE = "oshbocker_live_solution"
# features that make a forecast degrade silently when empty (CatBoost treats NaN as "missing" without complaint)
KEY_FEATURES = [
    "streamflow_deviation_30_mean",
    "combined_swe_deviation_0",
    "ua_swe_deviation",
    "acc_water_deviation",
    "precip_deviation_season_mean",
]


def _live(src_dir: Path):
    if _LIVE not in sys.modules:
        sys.path.insert(0, str(src_dir))  # `features`, `generate_predictions`, bundled `wsfr_download` resolve from here
        spec = importlib.util.spec_from_file_location(_LIVE, src_dir / "solution.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_LIVE] = module
        spec.loader.exec_module(module)
    return sys.modules[_LIVE]


def preprocess(src_dir: Path, data_dir: Path, preprocessed_dir: Path) -> dict:
    os.environ["WSFR_DATA_ROOT"] = str(data_dir)  # wsfr_read resolves metadata and streamflow from here
    Path(preprocessed_dir).mkdir(parents=True, exist_ok=True)
    return _live(Path(src_dir)).preprocess(Path(src_dir), Path(data_dir), Path(preprocessed_dir))


def predict(site_id: str, issue_date: str, assets: dict, src_dir: Path, data_dir: Path, preprocessed_dir: Path) -> tuple[float, float, float]:
    return _live(Path(src_dir)).predict(site_id, issue_date, assets, Path(src_dir), Path(data_dir), Path(preprocessed_dir))


def feature_report(paths: Paths, issue_date: date) -> list[str]:
    f = paths.preprocessed / "test_features.csv"
    if not f.exists():
        return ["preprocessed/test_features.csv not found: cannot check features"]
    df = pd.read_csv(f)
    df = df[df.issue_date == issue_date.isoformat()]
    out = []
    for col in KEY_FEATURES:
        if col in df:
            empty = sorted(df.loc[df[col].isna(), "site_id"])
            if empty:
                out.append(f"feature {col} is empty for {len(empty)} site(s): {empty}")
    return out


def run_forecast(paths: Paths, issue_date: date, sites: list[str] | None = None) -> tuple[pd.DataFrame, list[tuple[str, str]], list[str]]:
    paths.logs.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(paths.logs / f"predict_{issue_date.isoformat()}.log", level="INFO")

    meta = pd.read_csv(paths.data / "metadata.csv")
    assets = preprocess(paths.src, paths.data, paths.preprocessed)
    rows, errors, warnings = [], [], []
    for _, m in meta.iterrows():
        if sites and m.site_id not in sites:
            continue
        if issue_date.month > m.season_end_month:
            errors.append((m.site_id, "issue date is after the site's forecast season"))
            continue
        try:
            raw = [float(v) for v in predict(m.site_id, issue_date.isoformat(), assets, paths.src, paths.data, paths.preprocessed)]
            if any(pd.isna(v) for v in raw):
                raise ValueError("NaN quantile")
            q = sorted(raw)
            if q != raw:
                warnings.append(f"{m.site_id}: live quantiles were not ordered {tuple(round(v, 1) for v in raw)}; sorted")
            rows.append(dict(site_id=m.site_id, issue_date=issue_date.isoformat(), volume_10=q[0], volume_50=q[1], volume_90=q[2]))
        except Exception as e:  # noqa: BLE001
            errors.append((m.site_id, f"{type(e).__name__}: {e}"))
    warnings += feature_report(paths, issue_date)
    return schema.to_frame(rows), errors, warnings
