"""Inference path of the 3rd place (rasyidstat) final-stage ("overall") solution: 9 LightGBM variants -> `ens_all`.

The competition code in core/ (src/, configs/) is used unchanged. Its training script `train_cv.py` is a module-level
script, so the feature path it applies at prediction time is transcribed here step by step (same configs, same
`exclude_years`, same target scaling / diff, same per-basin SNOTEL/CDEC site ranking loaded from the saved model artifacts,
same Tweedie "reg" model as the p50, same `ens_all` ensemble from notebooks/eval_cv.ipynb).

Differences from the QC wrapper (models/rasyidstat_lgbm/forecast) this was promoted from:
  * no training code; the trained variants are read from assets/models;
  * only the forecast water year is read. Every feature of the model is a per (site, water year) quantity (lags, cumulative
    sums, forward fills, expand_date all group by wyear) and the training-derived statistics come from the saved artifacts,
    so the historical 1981-2023 caches of the training run are not needed;
  * variants whose inputs do not (yet) cover the issue date are reported and left out of the ensemble instead of silently
    producing no rows.

`bootstrap(src_dir)` must be called first: the vendored code reads `data/...` relative to the working directory and is
imported as the top-level package `src`.
"""

from __future__ import annotations

import copy
import datetime
import importlib
import json
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

VARIANTS = {
    "afs_base_syc": ["base_swe", "swe_ua", "pdsi_swe_s51", "pdsi_swe_era5", "pdsi_swe_era5_s51"],
    "afs_ngm_syc": ["ngm_ua", "ngm_pdsi_ua_s51", "ngm_pdsi_era5_s51", "ngm_pdsi_ua_era5_s51"],
}
ALL_VARIANTS = [v for vs in VARIANTS.values() for v in vs]
EXCLUDE_YEARS = [2011, 2015]
GROUP = ["site_id", "year", "month", "day", "md_id"]

_V = None  # the vendored modules, filled in by bootstrap()


def bootstrap(src_dir: Path) -> None:
    """chdir to the build directory, put the core on sys.path and import the vendored modules."""
    global _V
    if _V is not None:
        return
    src_dir = Path(src_dir).resolve()
    os.chdir(src_dir)
    sys.path.insert(0, str(src_dir))
    import lightgbm as lgb
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    mods = {"lgb": lgb}
    for name in (
        "src.config",
        "src.data.base",
        "src.features.base",
        "src.features.swe",
        "src.features.volume_obs",
        "src.models.ensemble",
        "src.models.lgb",
        "src.models.postprocess",
        "src.meta.get_available_sites",
    ):
        mods[name] = importlib.import_module(name)
    _V = mods


def _m(name):
    if _V is None:
        raise RuntimeError("engine.bootstrap(src_dir) must be called first")
    return _V[name]


def load_cfg(name: str) -> dict:
    """Overall-phase config of one variant with the settings train_cv.py applies for `-f True -e 2011 2015`."""
    # the variant modules mutate the cfg dict imported from base_swe, so every variant needs fresh modules
    for mod in [m for m in sys.modules if m.startswith("configs.main.")]:
        del sys.modules[mod]
    cfg = copy.deepcopy(importlib.import_module(f"configs.main.{name}").cfg)
    cfg["val_years"] = []
    cfg["test_years"] = []
    cfg["is_forecast"] = True
    cfg["exclude_years"] = EXCLUDE_YEARS
    return cfg


def _dt(s):
    return pd.to_datetime(s)


class VariantUnavailable(RuntimeError):
    """The inputs of a variant do not cover the issue date."""


class Sources:
    """The forecast water year's inputs. `as_of` drops every observation dated after it.

    Raw per-station files are read from data/external/<source>/ (= <root>/downloads); the gridded / spatially reduced
    caches (UA SWANN, PDSI, ERA5-Land, SEAS5.1) from `cache_dir` (= <root>/preprocessed, written by preprocess.py).
    """

    def __init__(self, forecast_year: int, cache_dir: Path, monthly_csv=None, as_of=None):
        self.forecast_years = [forecast_year]
        self.cache = Path(cache_dir)
        self.monthly_csv = None if monthly_csv is None else Path(monthly_csv)
        self.as_of = None if as_of is None else pd.Timestamp(as_of)
        self._c: dict = {}
        self.last: dict[str, pd.Timestamp] = {}  # latest observation per input, for the availability report

    def _cut(self, df, col):
        if self.as_of is None:
            return df
        return df[_dt(df[col]) <= self.as_of]

    def _note(self, key, series):
        s = _dt(series).dropna()
        if len(s):
            self.last[key] = max(self.last.get(key, s.max()), s.max())

    def _cached(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    @property
    def meta(self):
        return self._cached("meta", lambda: _m("src.data.base").read_meta("data/meta/metadata_proc.csv"))

    @property
    def df_train(self):
        def f():
            b, fb = _m("src.data.base"), _m("src.features.base")
            lab = b.read_train(meta=self.meta, is_forecast=True)
            new_years = [y for y in self.forecast_years if y not in set(lab["year"])]
            fc = fb.generate_base_year(self.meta, years=new_years).assign(volume=np.nan) if new_years else lab.iloc[:0]
            return pd.concat([lab, fc]).reset_index(drop=True)

        return self._cached("train", f)

    @property
    def df_monthly(self):
        def f():
            df = _m("src.data.base").read_monthly_naturalized_flow(is_forecast=True)
            if self.monthly_csv is not None and self.monthly_csv.exists():
                ext = pd.read_csv(self.monthly_csv)[list(df.columns)]
                ext = ext[ext["year"].isin(self.forecast_years) & ~ext["volume"].isna()]
                df = pd.concat([df, ext]).sort_values(["site_id", "year", "month"], kind="stable")
            return df.reset_index(drop=True)

        return self._cached("monthly", f)

    # --- SWE (SNOTEL + CDEC) -------------------------------------------------------------------------------
    def swe(self, cfg):
        key = ("swe", json.dumps(cfg["swe"], sort_keys=True), cfg["filter_snotel_sites"])
        return self._cached(key, lambda: self._swe(cfg))

    def _swe(self, cfg):
        c, b, fb = _m("src.config"), _m("src.data.base"), _m("src.features.base")
        sites = pd.read_feather("data/meta/snotel_sites_basins/snotel_sites_basins_chosen.feather")
        if cfg["filter_snotel_sites"]:
            sites = _m("src.meta.get_available_sites").filter_available_snotel_sites(sites)
        ids = sites.snotel_id.tolist()
        df_swe = b.read_snotel_swe(c.SNOTEL_SWE_DIR, ids)
        df_swe = df_swe.drop_duplicates(["snotel_id", "date"], keep="last")
        self._note("snotel", df_swe["date"])
        df_swe = self._cut(df_swe, "date")
        df_swe = fb.parse_time_features(df_swe, cols=["date"], level=["day", "yday", "month", "year", "wyear", "wyday"])
        ffill = cfg["swe"].get("ffill_limit")
        df_swe = (
            fb.forward_fill(df_swe, groupby_cols=["snotel_id", "wyear"], limit=ffill)
            if ffill
            else fb.forward_fill(df_swe, groupby_cols=["snotel_id", "wyear"])
        )
        if cfg["swe"].get("use_cdec"):
            sites_cdec = pd.read_feather("data/meta/cdec_sites_chosen.feather")
            cdec = b.read_cdec_swe(c.CDEC_SWE_DIR, is_preprocess=True)
            cdec = cdec.drop_duplicates(["cdec_id", "date"], keep="last")
            self._note("cdec", cdec["date"])
            cdec = self._cut(cdec, "date")
            cdec = fb.parse_time_features(cdec, cols=["date"], level=["day", "yday", "month", "year", "wyear", "wyday"])
            cdec = fb.forward_fill(cdec, groupby_cols=["cdec_id", "wyear"], limit=ffill if ffill else 7)
            df_swe = pd.concat([df_swe, cdec.rename(columns={"cdec_id": "snotel_id"})])
            sites = pd.concat([sites, sites_cdec.rename(columns={"station_id": "snotel_id"})])
        cols = ["snotel_id", "date", "day", "yday", "month", "year", "wyear"] + cfg["swe"]["features"]
        df_filtered, lag_features = fb.get_lag_features(
            df_swe[cols].query("swe==swe"),
            groupby_cols=["snotel_id", "wyear"],
            features=cfg["swe"]["features"],
            lag_list=cfg["swe"]["lag_list"],
        )
        return dict(df_swe=df_swe, df_filtered=df_filtered.drop(columns=["wyear"]), lag_features=lag_features, sites=sites)

    # --- UA-SWANN ------------------------------------------------------------------------------------------
    def uaswe(self, cfg):
        key = ("uaswe", json.dumps(cfg["uaswe"], sort_keys=True))
        return self._cached(key, lambda: self._uaswe(cfg))

    def _uaswe(self, cfg):
        fb = _m("src.features.base")
        huc = {}
        for level in (6, 8):
            df = pd.read_feather(self.cache / f"uaswe_huc{level}.feather")
            self._note(f"uaswann_huc{level}", df["date"])
            huc[level] = self._cut(df, "date").rename(columns={"swe": f"uaswe_huc{level}", "prec_cml": f"uaprec_cml_huc{level}"})
        basin = pd.read_csv(self.cache / "uaswe_basin.csv")
        basin = basin.groupby(["site_id", "time"], as_index=False).last()
        basin = basin.rename(columns={"time": "date", "SWE": "uaswe", "DEPTH": "uasdepth"})
        self._note("uaswann_basin", basin["date"])
        basin = fb.parse_time_features(self._cut(basin, "date"), level=[])
        df = pd.merge(huc[6], huc[8])
        df = pd.merge(df, basin)
        df = fb.parse_time_features(df)
        df = fb.expand_date(df, groupby_cols=["site_id", "wyear"], max_mm_dd="07-22")
        df = fb.parse_time_features(df)
        feats, lag_features = fb.get_lag_features(
            df[["site_id", "date", "day", "yday", "month", "year", "wyear"] + cfg["uaswe"]["features"]],
            groupby_cols=["site_id", "wyear"],
            features=cfg["uaswe"]["features"],
            lag_list=cfg["uaswe"]["lag_list"],
        )
        return feats.drop(columns=cfg["uaswe"]["features"] + ["date", "wyear"]), lag_features

    # --- PDSI ----------------------------------------------------------------------------------------------
    def pdsi(self, cfg):
        key = ("pdsi", json.dumps(cfg["pdsi"], sort_keys=True))
        return self._cached(key, lambda: self._pdsi(cfg))

    @staticmethod
    def _anchor_calendar_year(df, fb):
        """expand_date ends each water year at 07-22 of the *last observation's* calendar year. When the newest PDSI row
        is still dated in Oct-Dec (a Jan-1 issue) that range is empty and the merge fails. A NaN row on Jan 1 of the
        water year fixes the range; the later ffill makes it a no-op."""
        last = df.groupby(["site_id", "wyear"], as_index=False)["date"].max()
        last = last[last["date"] < pd.to_datetime(last["wyear"].astype(str) + "-01-01")]
        if last.empty:
            return df
        extra = last.assign(date=pd.to_datetime(last["wyear"].astype(str) + "-01-01"), pdsi=np.nan)[["site_id", "date", "pdsi"]]
        extra = fb.parse_time_features(extra, cols=["date"])
        return pd.concat([df, extra], ignore_index=True)

    def _pdsi(self, cfg):
        fb = _m("src.features.base")
        df = pd.read_csv(self.cache / "pdsi.csv").drop_duplicates()
        self._note("pdsi", df["date"])
        df = fb.parse_time_features(self._cut(df, "date"), cols=["date"])
        df = self._anchor_calendar_year(df, fb)
        df = df.sort_values(["site_id", "date"]).reset_index(drop=True)
        expanded = fb.expand_date(df, groupby_cols=["site_id", "wyear"], max_mm_dd="07-22")
        expanded = fb.parse_time_features(expanded, cols=["date"])
        expanded = expanded.assign(pdsi=lambda x: x.groupby(["site_id", "wyear"])["pdsi"].transform("ffill"))
        feats, lag_features = fb.get_lag_features(
            expanded[["site_id", "date", "day", "yday", "month", "year", "wyear"] + cfg["pdsi"]["features"]],
            groupby_cols=["site_id", "wyear"],
            features=cfg["pdsi"]["features"],
            lag_list=cfg["pdsi"]["lag_list"],
        )
        feats = feats.query("month in [1,2,3,4,5,6,7]").drop(columns=["pdsi", "date", "wyear"])
        return feats, lag_features

    # --- SEAS5.1 / ERA5-Land -------------------------------------------------------------------------------
    def seas51(self, cfg):
        key = ("s51", json.dumps(cfg["cds"]["s51"], sort_keys=True), cfg["cds"].get("use_same_ens"))
        return self._cached(key, lambda: self._seas51(cfg))

    def _seas51(self, cfg):
        fb = _m("src.features.base")
        df = pd.read_feather(self.cache / "seas51.feather")
        self._note("seas51_init", df["date"])
        df = self._cut(df, "date").copy()
        df["t2m"] = df["t2m"] - 273.15
        df = df.dropna()
        if cfg["cds"].get("use_same_ens"):
            df = df.query("number < 25")
        agg, agg_features = fb.get_agg_features(
            df,
            groupby_cols=["site_id", "date"],
            features=cfg["cds"]["s51"]["features"],
            agg_cols=cfg["cds"]["s51"]["agg_cols"],
        )
        agg = fb.parse_time_features(agg, level=["wyear", "month"])
        expanded = fb.get_month_features(agg, ["site_id", "wyear"], agg_features)
        expanded = expanded.rename(columns={"wyear": "year"}).drop(columns=["date"]).query("month != 12")
        return expanded.dropna(), agg_features

    def era5(self, cfg):
        key = ("era5", json.dumps(cfg["cds"]["era5"], sort_keys=True))
        return self._cached(key, lambda: self._era5(cfg))

    def _era5(self, cfg):
        fb = _m("src.features.base")
        df = pd.read_feather(self.cache / "era5.feather")
        df = df.assign(
            time=lambda x: pd.to_datetime(x["time"]),
            date=lambda x: x["time"].dt.date,
            hour=lambda x: x["time"].dt.hour,
        )
        self._note("era5land_hour0", df.loc[df["hour"] == 0, "time"])
        df = self._cut(df, "time").copy()
        df["t2m"] = df["t2m"] - 273.15
        df = df.assign(date=lambda x: x["date"] + datetime.timedelta(days=1))
        df = fb.parse_time_features(df, level=["wyear", "month", "day"])
        df = df[df["hour"] == cfg["cds"]["era5"]["hour"]]
        feats = cfg["cds"]["era5"]["features"]
        df = df.rename(columns={"wyear": "year"})
        return df[["site_id", "year", "month", "day"] + feats], feats

    # --- USGS / USBR observed flow -------------------------------------------------------------------------
    @property
    def volume_obs(self):
        return self._cached("volobs", self._volume_obs)

    def _volume_obs(self):
        b, vo, fb = _m("src.data.base"), _m("src.features.volume_obs"), _m("src.features.base")
        usbr = vo.prepare_usbr_data("data/external/usbr")
        usgs = vo.prepare_usgs_data(self.meta, "data/external/usgs_streamflow", usgs_format="csv")
        usbr["date"] = _dt(usbr["date"])
        usgs["date"] = _dt(usgs["date"])
        usgs = usgs.drop_duplicates(["site_id", "date"], keep="last")
        usbr = usbr.groupby(["site_id", "date"], as_index=False).agg(volume_obs=("volume_obs", "sum"))
        self._note("usgs_streamflow", usgs["date"])
        self._note("usbr", usbr["date"])
        df = pd.concat(
            [
                usbr[["date", "site_id", "volume_obs"]].assign(source="usbr"),
                usgs[["date", "site_id", "volume_obs"]].assign(source="usgs"),
            ]
        )
        df = self._cut(df, "date")
        df = fb.parse_time_features(df)
        df = fb.expand_date(df, groupby_cols=["site_id", "wyear"])
        df = fb.parse_time_features(df)
        df = fb.forward_fill(df, groupby_cols=["site_id", "wyear"])
        return vo.prepare_volume_obs_diff(df, self.meta)


def build_features(src: Sources, cfg: dict, art: dict, dates: list[pd.Timestamp] | None = None):
    """Feature table for every (site, date) of the forecast year (or only `dates`), using the saved artifacts `art`."""
    fb, vo, b, sw = _m("src.features.base"), _m("src.features.volume_obs"), _m("src.data.base"), _m("src.features.swe")
    cfg = copy.deepcopy(cfg)
    fy = src.forecast_years
    df_train = fb.get_year_cat(src.df_train, val_years=fy, test_years=[])
    df_train_base = fb.generate_base_train(src.df_train, use_new_format=True)
    if cfg["target_prep"]["diff"]:
        df_train_base = fb.get_volume_target_diff(
            df_train_base, fb.generate_target_diff(src.df_monthly, src.meta), cfg["diff_gap"]
        )
        cfg["remove_features"] = cfg["remove_features"] + ["volume_actual", "diff", "month_tf"]
    if cfg["target_prep"].get("diff_extra"):
        df_train_base = vo.get_volume_target_diff_extra(df_train_base, src.volume_obs)
    df_train_base = fb.get_year_cat(df_train_base, val_years=fy, test_years=[])
    df_train_base = df_train_base[df_train_base["year"].isin(fy)]
    if dates is not None:
        keep = {(d.year, d.month, d.day) for d in dates}
        df_train_base = df_train_base[[(y, m, d) in keep for y, m, d in zip(df_train_base.year, df_train_base.month, df_train_base.day)]]
    df_train_all = df_train_base.copy()

    train_stats = art["train_stats"]
    train_stats_cols = [c for c in train_stats.columns if c != "site_id"]
    if cfg["target_prep"]["scale"] == "max":
        df_train_all = pd.merge(df_train_all, train_stats).assign(volume=lambda x: x["volume"] / x["volume_max"])
    if len(set(train_stats_cols) & set(cfg["remove_features"])) == 0:
        cfg["remove_features"] = cfg["remove_features"] + train_stats_cols

    features = []
    if cfg.get("swe"):
        s = src.swe(cfg)
        df_swe, df_filtered, lag_features, sites = s["df_swe"], s["df_filtered"], s["lag_features"], s["sites"]
        swe_stats = art["swe_stats"]
        swe_stats_cols = [c for c in swe_stats.columns if c != "snotel_id"]
        df_mm = pd.merge(df_filtered, swe_stats)
        for feature in cfg["swe"]["features"]:
            for lag_feature in lag_features:
                if lag_feature.startswith(feature):
                    if cfg["swe"]["scale"] == "minmax":
                        df_mm[lag_feature] = df_mm[lag_feature] / df_mm[feature + "_max"]
                    elif cfg["swe"]["scale"] == "norm":
                        df_mm[lag_feature] = (df_mm[lag_feature] - df_mm[feature + "_mean"]) / df_mm[feature + "_std"]
        df_mm = df_mm.drop(columns=swe_stats_cols)
        out = []
        for site_id in src.meta.site_id:
            selected = art["selected"][site_id]
            res = (
                sw.get_basin_swe(
                    df_train[df_train["year"].isin(fy)][["site_id", "year"]],
                    df_mm.query("swe==swe & month in [1,2,3,4,5,6,7]"),
                    sites[["snotel_id", "site_id"]],
                    site_id=site_id,
                )
                .query("snotel_id in @selected")
                .drop(columns=["snotel_id"] + cfg["swe"]["features"])
                .groupby(["site_id", "date", "year", "month", "day"], as_index=False)
                .mean()
                .drop(columns=["date"])
            )
            out.append(res)
        df_swe_features = pd.concat(out)
        if cfg["swe"].get("extra_features"):
            raise NotImplementedError("extra_features are not used by any overall-phase variant")
        df_train_all = pd.merge(df_train_all, df_swe_features, how="left")
        df_train_all = df_train_all.query("year >= @year_min", local_dict={"year_min": cfg.get("year_min", 1980)})
        df_train_all = df_train_all.query("yday == yday").reset_index(drop=True)
        features = features + lag_features

    if cfg.get("uaswe"):
        feats, lag_features = src.uaswe(cfg)
        df_train_all = pd.merge(df_train_all, feats, how="inner")
        features = features + lag_features
    if cfg.get("pdsi"):
        feats, lag_features = src.pdsi(cfg)
        df_train_all = pd.merge(df_train_all, feats, how="inner")
        features = features + lag_features
    if cfg.get("cds"):
        if cfg["cds"].get("s51"):
            feats, agg_features = src.seas51(cfg)
            df_train_all = pd.merge(df_train_all, feats, how="inner")
            features = features + agg_features
        if cfg["cds"].get("era5"):
            feats, era5_features = src.era5(cfg)
            df_train_all = pd.merge(df_train_all, feats, how="inner")
            features = features + era5_features

    df_train_all = fb.get_meta_features(df_train_all, src.meta)
    df_train_all = df_train_all[
        ((df_train_all["cat"] == "train") & (df_train_all["year"].isin(cfg["exclude_years"]))) == False  # noqa: E712
    ]
    return df_train_all, features, art, cfg


def load_art(model_dir: Path) -> dict:
    art = {"train_stats": pd.read_csv(model_dir / "train_stats.csv")}
    if (model_dir / "swe_stats.csv").exists():
        art["swe_stats"] = pd.read_csv(model_dir / "swe_stats.csv", dtype={"snotel_id": "object"})
        art["selected"] = json.load(open(model_dir / "selected_sites.json"))
    return art


def predict_variant(src: Sources, name: str, model_root: Path, dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Rescaled (volume_max) + diff-added predictions of one variant for every site at `dates`."""
    lgb, lg, pp = _m("lgb"), _m("src.models.lgb"), _m("src.models.postprocess")
    model_dir = Path(model_root) / name
    cfg = load_cfg(name)
    df, _, _, cfg = build_features(src, cfg, load_art(model_dir), dates)
    df = df[df["cat"] == "val"].reset_index(drop=True)
    if df.empty:
        raise VariantUnavailable("no feature rows for the issue date (an input does not cover it)")
    features = pd.read_csv(model_dir / "feature_names.csv")["features"].tolist()
    x = lg.as_categorical(df, cfg["cat_features"])[features]
    pred = df[["site_id"] + cfg["remove_features"] + ["month", "day"]].copy()
    for q in (50, 10, 90):
        pred[f"pred_volume_{q}"] = lgb.Booster(model_file=f"{model_dir}/{name}_all_p{q}.bin").predict(x)
    pred["pred_volume_reg"] = lgb.Booster(model_file=f"{model_dir}/{name}_reg_all_p50.bin").predict(x)
    pred = pp.rescale(pred, method=cfg["target_prep"]["scale"])
    if cfg["target_prep"]["diff"]:
        pred = pp.add_diff(pred)
    pred["pred_volume_50"] = pred["pred_volume_reg"]
    return pred.assign(exp_name=name)


def ensemble(preds: list[pd.DataFrame]) -> pd.DataFrame:
    """ens_all of the final solution: all variants, q10/q90 percentile, q50 mean."""
    pp, en = _m("src.models.postprocess"), _m("src.models.ensemble")
    df = pd.concat(preds)
    df = df.query('(site_id=="detroit_lake_inflow" & md_id>=24)==False')
    df = pp.rearrange_prediction(df)
    return pp.rearrange_prediction(en.custom_ensemble(df, groupby_cols=GROUP))


def to_submission(ens: pd.DataFrame) -> pd.DataFrame:
    out = ens.assign(
        issue_date=lambda x: pd.to_datetime(
            x["year"].astype(str) + "-" + x["month"].astype(str) + "-" + x["day"].astype(str)
        ).dt.strftime("%Y-%m-%d"),
        volume_10=lambda x: x["pred_volume_10"],
        volume_50=lambda x: x["pred_volume_50"],
        volume_90=lambda x: x["pred_volume_90"],
    )
    return out[["site_id", "issue_date", "volume_10", "volume_50", "volume_90"]].sort_values(["issue_date", "site_id"])


@dataclass
class ForecastResult:
    forecast: pd.DataFrame
    used: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)
    sites_per_variant: dict[str, int] = field(default_factory=dict)
    last_obs: dict[str, pd.Timestamp] = field(default_factory=dict)


def forecast(
    issue_date: datetime.date,
    model_root: Path,
    cache_dir: Path,
    monthly_csv: Path | None = None,
    variants: list[str] | None = None,
) -> ForecastResult:
    """Ensemble forecast for one issue date from observations dated up to it (as_of = issue date; every feature lags >= 1 day)."""
    d = pd.Timestamp(issue_date)
    src = Sources(d.year, cache_dir, monthly_csv, as_of=d)
    preds, res = [], ForecastResult(forecast=pd.DataFrame())
    for v in variants or ALL_VARIANTS:
        try:
            p = predict_variant(src, v, model_root, [d])
        except (VariantUnavailable, FileNotFoundError) as e:
            res.dropped[v] = f"{type(e).__name__}: {e}"
            continue
        preds.append(p)
        res.used.append(v)
        res.sites_per_variant[v] = p.site_id.nunique()
    res.last_obs = dict(src.last)
    if preds:
        sub = to_submission(ensemble(preds))
        res.forecast = sub[sub["issue_date"] == d.strftime("%Y-%m-%d")].reset_index(drop=True)
    return res
