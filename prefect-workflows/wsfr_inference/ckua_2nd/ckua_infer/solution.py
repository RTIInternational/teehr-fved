"""Competition-style interface over the unmodified live-stage `solution.py` (built into <root>/build/src).

    preprocess(src_dir, data_dir, preprocessed_dir) -> assets
    predict(site_id, issue_date, assets, src_dir, data_dir, preprocessed_dir) -> (q10, q50, q90)   # KAF
    run_forecast(paths, issue_date, sites=None) -> (forecasts DataFrame, errors list)

The live code asserts on negative / mis-ordered quantiles; run_forecast records those as errors instead of writing them.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning

from . import schema
from .paths import Paths

# multiscaler.pkl / snotel_lrs.pkl were pickled with sklearn 1.3.2; on newer sklearn every load warns. Forecasts were checked
# to match the pinned environment (see CHANGES.md), so this one warning is silenced; all other warnings stay visible.
warnings.filterwarnings("ignore", category=InconsistentVersionWarning)


@contextlib.contextmanager
def _in_src(src_dir: Path):
    """The live code is written to run from its own directory (relative config paths, `libs` imports)."""
    old_cwd, old_path = os.getcwd(), list(sys.path)
    os.chdir(src_dir)
    sys.path.insert(0, str(src_dir))
    try:
        yield
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def _live(src_dir: Path):
    name = "ckua_live_solution"
    if name not in sys.modules:
        with _in_src(src_dir):
            spec = importlib.util.spec_from_file_location(name, src_dir / "solution.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
    return sys.modules[name]


def preprocess(src_dir: Path, data_dir: Path, preprocessed_dir: Path) -> dict:
    with _in_src(Path(src_dir)), contextlib.redirect_stdout(io.StringIO()):
        return _live(Path(src_dir)).preprocess(Path(src_dir), Path(data_dir), Path(preprocessed_dir))


def predict(site_id: str, issue_date: str, assets: dict, src_dir: Path, data_dir: Path, preprocessed_dir: Path) -> tuple[float, float, float]:
    src_dir = Path(src_dir)
    with _in_src(src_dir), contextlib.redirect_stdout(io.StringIO()):
        return _live(src_dir).predict(site_id, issue_date, assets, src_dir, Path(data_dir), Path(preprocessed_dir))


def run_forecast(paths: Paths, issue_date: date, sites: list[str] | None = None) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    meta = pd.read_csv(paths.data / "metadata.csv")
    assets = preprocess(paths.src, paths.data, paths.preprocessed)
    rows, errors = [], []
    for _, m in meta.iterrows():
        if sites and m.site_id not in sites:
            continue
        if issue_date.month > m.season_end_month and issue_date.month < 10:
            errors.append((m.site_id, "issue date is after the site's forecast season"))
            continue
        try:
            q10, q50, q90 = predict(m.site_id, issue_date.isoformat(), assets, paths.src, paths.data, paths.preprocessed)
            rows.append(dict(site_id=m.site_id, issue_date=issue_date.isoformat(), volume_10=float(q10), volume_50=float(q50), volume_90=float(q90)))
        except Exception as e:  # noqa: BLE001 - the live code raises AssertionError on bad inputs
            errors.append((m.site_id, f"{type(e).__name__}: {e}"))
    return schema.to_frame(rows), errors
