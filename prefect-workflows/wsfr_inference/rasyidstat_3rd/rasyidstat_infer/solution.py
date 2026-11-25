"""Competition-style interface over the engine.

    preprocess(paths, issue_date)                          raw downloads -> feature caches
    predict(paths, issue_date, sites=None)                 -> (forecasts DataFrame, errors, warnings)   # KAF
    run_forecast = predict

Real-time availability: the sources have different latencies (ERA5-Land ~5 days, UA SWANN ~2 days, SEAS5.1 published ~5th of the
month, SNOTEL/USGS/CDEC/PDSI ~1 day), so on the issue date itself only some variants can run. A variant whose inputs do not
cover the issue date is left out of the ensemble (never filled from stale data) and the output `model_version` says which
variants were used. `strict=True` turns any left-out variant into an error.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from . import engine, schema
from .paths import MODEL_VERSION, Paths
from .preprocess import preprocess as _preprocess

# sources whose newest observation should be the day before the issue date; older = stale
DAILY_SOURCES = {"snotel": 1, "cdec": 1, "usgs_streamflow": 1, "pdsi": 7, "uaswann_basin": 1, "uaswann_huc6": 1, "uaswann_huc8": 1}


def preprocess(paths: Paths, issue_date: date, steps: list[str] | None = None) -> None:
    _preprocess(paths, issue_date, steps)


def model_version(used: list[str]) -> str:
    if sorted(used) == sorted(engine.ALL_VARIANTS):
        return MODEL_VERSION
    return f"{MODEL_VERSION}_partial{len(used)}of{len(engine.ALL_VARIANTS)}"


def source_report(last_obs: dict, issue_date: date) -> list[str]:
    """Inputs whose newest observation is older than the lag the model is trained for."""
    out, want = [], pd.Timestamp(issue_date) - pd.Timedelta(days=1)
    for key, slack in DAILY_SOURCES.items():
        if key not in last_obs:
            out.append(f"input {key}: no data")
        elif last_obs[key] < want - pd.Timedelta(days=slack - 1):
            out.append(f"input {key}: newest observation {last_obs[key].date()} (issue date {issue_date})")
    return out


def predict(paths: Paths, issue_date: date, sites: list[str] | None = None, strict: bool = False):
    paths.logs.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(paths.logs / f"predict_{issue_date.isoformat()}.log", level="INFO")
    engine.bootstrap(paths.src)
    errors, warnings = [], []
    monthly = paths.data / "test_monthly_naturalized_flow.csv"
    if not monthly.exists():
        warnings.append("test_monthly_naturalized_flow.csv missing: running without monthly flow")
    res = engine.forecast(issue_date, paths.assets / "models", paths.preprocessed, monthly if monthly.exists() else None)
    for v, why in res.dropped.items():
        msg = f"variant {v} left out: {why}"
        (errors if strict else warnings).append(("ensemble", msg) if strict else msg)
    if not res.used:
        errors.append(("ensemble", "no variant could run for this issue date"))
        return schema.to_frame([]), errors, warnings
    warnings += source_report(res.last_obs, issue_date)
    df = res.forecast
    meta = pd.read_csv(paths.data / "metadata.csv")
    expected = set(meta.site_id)
    if sites:
        expected &= set(sites)
        df = df[df.site_id.isin(sites)]
    for site in sorted(expected - set(df.site_id)):
        errors.append((site, "no forecast produced"))
    partial = {v: n for v, n in res.sites_per_variant.items() if n < len(meta)}
    if partial:
        warnings.append(f"variants with fewer than {len(meta)} sites: {partial}")
    rows = df[["site_id", "issue_date", "volume_10", "volume_50", "volume_90"]].to_dict("records")
    return schema.to_frame(rows, model_version(res.used)), errors, warnings


run_forecast = predict
