"""Reduce the raw downloads (<root>/downloads) to the feature caches the model reads (<root>/preprocessed).

The spatial reductions are the competition's own `preprocess_*` functions (same polygons, same averaging) run unchanged.
Caches only cover the forecast water year, which is all the model needs (see engine.py). Heavy steps are incremental:
a state file records what was already reduced, so a daily run only processes new or re-downloaded files.

    pdsi.csv            site_id, date, pdsi
    uaswe_huc{6,8}.feather   site_id, date, swe, prec_cml            (HUC watershed time series)
    uaswe_basin.csv     site_id, time, SWE, DEPTH                   (gridded 4 km daily NetCDF clipped to the basin polygons)
    era5.feather        site_id, time, <ERA5-Land variables>        (00:00 and 23:00 UTC of each downloaded day)
    seas51.feather      site_id, date, number, <SEAS5.1 variables>  (one initialisation per month)
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import shutil
import tempfile
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

from . import engine
from .paths import Paths

warnings.filterwarnings("ignore")
BASIN_CHUNK = 20


def _state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _sig(f: Path) -> list:
    s = f.stat()
    return [s.st_size, s.st_mtime_ns]


def _wy_start(issue_date: date) -> pd.Timestamp:
    return pd.Timestamp(f"{issue_date.year - 1}-10-01")


def pdsi(paths: Paths, issue_date: date) -> pd.DataFrame | None:
    from src.data.base import read_meta_geo
    from src.features.pdsi import preprocess_pdsi

    if not glob.glob(str(paths.downloads / "pdsi" / "**" / "*.nc"), recursive=True):
        return None
    return preprocess_pdsi(str(paths.downloads / "pdsi"), read_meta_geo()[0], out_file=str(paths.preprocessed / "pdsi.csv"))


def uaswe_huc(paths: Paths, issue_date: date) -> None:
    from src.data.base import read_meta
    from src.features.uaswe import preprocess_uaswe_huc

    df_meta = read_meta("data/meta/metadata_proc.csv")
    sites = pd.read_feather("data/meta/nwis_usgs_meta.feather")
    sites["huc"] = sites["huc_cd"].astype(str).str.zfill(8)
    sites["huc8"] = sites["huc"].str[0:8]
    sites["huc6"] = sites["huc"].str[0:6]
    for level in (6, 8):
        if not glob.glob(str(paths.downloads / "uaswann" / "raw" / f"huc{level}" / "*.csv")):
            continue
        df = preprocess_uaswe_huc(str(paths.downloads / "uaswann"), df_meta, sites, huc_level=level, date="2100-01-01")
        df = df[pd.to_datetime(df["date"]) >= _wy_start(issue_date)].reset_index(drop=True)
        df.to_feather(paths.preprocessed / f"uaswe_huc{level}.feather")


def _basin_chunk(files: list[str]) -> pd.DataFrame:
    from src.data.base import read_meta_geo
    from src.features.uaswe import preprocess_uaswe_basin

    tmp = tempfile.mkdtemp(prefix="uaswe_")
    try:
        os.makedirs(f"{tmp}/raw/daily")
        for f in files:
            os.symlink(os.path.abspath(f), f"{tmp}/raw/daily/{os.path.basename(f)}")
        return preprocess_uaswe_basin(tmp, read_meta_geo()[0], level="daily")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uaswe_basin(paths: Paths, issue_date: date, procs: int = 8) -> None:
    out, state_f = paths.preprocessed / "uaswe_basin.csv", paths.preprocessed / "uaswe_basin.state.json"
    files = sorted(Path(f) for f in glob.glob(str(paths.downloads / "uaswann" / "raw" / "daily" / "*.nc")))
    state = _state(state_f) if out.exists() else {}
    todo = [f for f in files if state.get(f.name) != _sig(f)]
    if not todo:
        return
    chunks = [[str(f) for f in todo[i : i + BASIN_CHUNK]] for i in range(0, len(todo), BASIN_CHUNK)]
    with mp.get_context("spawn").Pool(min(procs, len(chunks)), maxtasksperchild=1) as pool:
        new = pd.concat(pool.map(_basin_chunk, chunks)).reset_index(drop=True)
    if out.exists() and state:
        old = pd.read_csv(out)
        new_days = set(pd.to_datetime(new["time"]).dt.strftime("%Y-%m-%d"))
        old = old[~pd.to_datetime(old["time"]).dt.strftime("%Y-%m-%d").isin(new_days)]
        new = pd.concat([old, new]).reset_index(drop=True)
    new.to_csv(out, index=False)
    state.update({f.name: _sig(f) for f in todo})
    state_f.write_text(json.dumps(state))


def era5(paths: Paths, issue_date: date) -> None:
    from src.data.base import read_meta_geo
    from src.features.era5 import preprocess_era5

    out, state_f = paths.preprocessed / "era5.feather", paths.preprocessed / "era5.state.json"
    files = sorted(glob.glob(str(paths.downloads / "era5" / "raw" / "**" / "*.nc"), recursive=True))
    state = _state(state_f) if out.exists() else {}
    todo = [f for f in files if state.get(os.path.relpath(f, paths.downloads)) != _sig(Path(f))]
    if not todo:
        return
    polys = read_meta_geo()[0]
    frames = [preprocess_era5(f, polys, is_new_cds=True) for f in todo]
    new = pd.concat(frames).reset_index()
    if out.exists() and state:
        old = pd.read_feather(out)
        new = pd.concat([old, new]).drop_duplicates(["site_id", "time"], keep="last")
    new.reset_index(drop=True).to_feather(out)
    state.update({os.path.relpath(f, paths.downloads): _sig(Path(f)) for f in todo})
    state_f.write_text(json.dumps(state))


def seas51(paths: Paths, issue_date: date) -> None:
    from src.data.base import read_meta_geo
    from src.features.seas51 import preprocess_seas51

    out, state_f = paths.preprocessed / "seas51.feather", paths.preprocessed / "seas51.state.json"
    raw = paths.downloads / "seas51" / "raw"
    pnames = sorted({f.name.split("_1_", 1)[1][:-3] for f in raw.glob("seas51_*_1_forecast_m1_*.nc")})
    state = _state(state_f) if out.exists() else {}
    polys = read_meta_geo()[0]
    frames = []
    for p in pnames:
        files = list(raw.glob(f"seas51_*_1_{p}.nc"))
        if len(files) != 7:  # a month that is only partly downloaded is not usable
            continue
        sig = [_sig(f) for f in sorted(files)]
        if state.get(p) == sig:
            continue
        frames.append(preprocess_seas51(str(paths.downloads / "seas51"), polys, pname=f"1_{p}"))
        state[p] = sig
    if not frames:
        return
    new = pd.concat(frames)
    if out.exists():
        old = pd.read_feather(out)
        new = pd.concat([old[~old["date"].isin(new["date"].unique())], new])
    new.reset_index(drop=True).to_feather(out)
    state_f.write_text(json.dumps(state))


STEPS = {"pdsi": pdsi, "uaswe_huc": uaswe_huc, "uaswe_basin": uaswe_basin, "era5": era5, "seas51": seas51}


def preprocess(paths: Paths, issue_date: date, steps: list[str] | None = None) -> None:
    """Needs the built core (`build`): the vendored functions read data/meta and data/raw relative to build/src."""
    paths.preprocessed.mkdir(parents=True, exist_ok=True)
    engine.bootstrap(paths.src)
    for name in steps or STEPS:
        print(f"preprocess {name}", flush=True)
        STEPS[name](paths, issue_date)
