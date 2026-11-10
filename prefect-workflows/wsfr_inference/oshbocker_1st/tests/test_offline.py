"""Offline tests (no network, no weights needed unless noted).

Network/regression tests live in test_regression.py and are opt-in (see that file).
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from oshbocker_infer import build, monthly_flow, schema
from oshbocker_infer.paths import Paths


def test_core_matches_manifest():
    assert build.check_core() == []


def test_core_tamper_detected(tmp_path):
    (tmp_path / "solution.py").write_text("x")
    assert any(p.startswith("missing") for p in build.verify_manifest(tmp_path, build.CORE_MANIFEST))


def test_patches_apply_and_fix_endpoints(tmp_path):
    import shutil
    import subprocess

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    swann = (tmp_path / "src/features/ua_swann_deviation.py").read_text()
    assert "snowview.arizona.edu" in swann and "verify=False" not in swann
    assert "https://data.rcc-acis.org" in (tmp_path / "src/features/acis.py").read_text()
    assert (tmp_path / "src/wsfr_download/__init__.py").exists()


def test_patched_swann_reads_current_format(tmp_path, monkeypatch):
    """The patched UA SWANN reader accepts the current snowview.arizona.edu CSV (comment header, 5 columns)."""
    import importlib.util
    import shutil
    import subprocess

    import requests

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    spec = importlib.util.spec_from_file_location("swann_patched", tmp_path / "src/features/ua_swann_deviation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    days = pd.date_range("2024-10-01", "2026-03-01")
    body = "# dataset: National SnowView\n# date_range: x\ndate,water_year,overall_cumulative_precip_in,overall_mean_swe_in,overall_snow_covered_area_sq_mi\n"
    body += "".join(f"{d:%Y-%m-%d},{d.year},{i % 7},{i % 5},0.0\n" for i, d in enumerate(days))

    class R:
        text = body

        def raise_for_status(self):
            pass

    urls = []
    monkeypatch.setattr(requests, "get", lambda url, **kw: urls.append(url) or R())
    feats = pd.DataFrame({"site_id": ["libby_reservoir_inflow"], "issue_date": ["2026-03-01"]})
    out = mod.generate_ua_swann_deviation(tmp_path, feats, "2026-03-01")
    assert urls == ["https://snowview.arizona.edu/csv/Download/Watersheds/17010101.csv"]
    assert {"ua_swe_deviation", "acc_water_deviation"} <= set(out.columns)


def _patched_src(tmp_path):
    import shutil
    import subprocess

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    return tmp_path / "src"


def test_pandas_version_independent_idioms_patched(tmp_path):
    src = _patched_src(tmp_path)
    for f in (src / "features").glob("*.py"):
        assert "np.mean, np.std" not in f.read_text(), f"{f.name}: np.std means ddof=0 on pandas 3 but ddof=1 on pandas 2"
    assert "element_means.iloc[idx]" in (src / "features/cdec_deviation.py").read_text()


def test_streamflow_30_day_feature_is_chronological(tmp_path, monkeypatch):
    """The last-30-days feature must not depend on the row order of the history (training sorts by site_id, datetime)."""
    import importlib.util
    import sys
    import types

    import numpy as np

    src = _patched_src(tmp_path)
    stub = types.ModuleType("wsfr_read.streamflow")
    stub.read_usgs_streamflow_data = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network in tests"))
    dl = types.ModuleType("wsfr_download.usgs_streamflow")
    dl.download_alternative_usgs_streamflow = lambda *a, **k: None
    dl.ALTERNATIVE_USGS_IDS = {}
    monkeypatch.setitem(sys.modules, "wsfr_read.streamflow", stub)
    monkeypatch.setitem(sys.modules, "wsfr_download.usgs_streamflow", dl)
    spec = importlib.util.spec_from_file_location("streamflow_patched", src / "features/streamflow_deviation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rng = np.random.default_rng(0)
    days = pd.date_range("2019-10-01", "2026-03-31")
    hist = pd.DataFrame({
        "datetime": days,
        "discharge_cfs_mean": 100 + 20 * np.sin(days.day_of_year / 58) + rng.normal(0, 5, len(days)),
        "site_id": "s1",
    })
    (tmp_path / "feature_parameters").mkdir()
    pre = tmp_path / "pre"
    pre.mkdir()
    hist.sample(frac=1, random_state=1).to_csv(tmp_path / "feature_parameters/train_streamflow.csv", index=False)

    feats = pd.DataFrame({"site_id": ["s1"], "year": [2026], "issue_date": ["2026-04-01"]})
    out = mod.generate_streamflow_deviation(tmp_path, pre, feats)

    md = hist["datetime"].dt.strftime("%m%d")
    g = hist.groupby(md)["discharge_cfs_mean"]
    dev = (hist["discharge_cfs_mean"] - g.transform("mean")) / g.transform("std")  # sample std, like the 'std' aggregation
    window = dev[(hist["datetime"] >= "2025-10-01") & (hist["datetime"] < "2026-04-01")]
    assert out["streamflow_deviation_30_mean"].iloc[0] == pytest.approx(window.iloc[-30:].mean())
    assert out["streamflow_deviation_season_mean"].iloc[0] == pytest.approx(window.mean())


def test_assets_checksums_if_present():
    paths = Paths.from_root()
    if not paths.assets.is_dir():
        pytest.skip("assets not fetched")
    assert build.check_assets(paths) == []


def test_forecast_year_and_complete_months():
    assert monthly_flow.forecast_year(date(2026, 1, 1)) == 2026
    assert monthly_flow.forecast_year(date(2025, 10, 1)) == 2026
    # a month is only usable once it has fully ended before the issue date
    assert monthly_flow.expected_months(date(2026, 3, 1)) == [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    assert not monthly_flow._month_ended(2026, 3, date(2026, 3, 31))
    assert monthly_flow._month_ended(2026, 3, date(2026, 4, 1))


def test_schema_validation():
    ok = schema.to_frame([dict(site_id="a", issue_date="2026-03-01", volume_10=1.0, volume_50=2.0, volume_90=3.0)])
    assert schema.validate(ok) == []
    bad = ok.assign(volume_10=5.0)
    assert "quantiles not ordered" in schema.validate(bad)
    assert list(ok.columns) == schema.COLUMNS


def test_leakage_report_flags_future_rows(tmp_path):
    from oshbocker_infer import download

    paths = Paths(tmp_path)
    (paths.data / "snotel" / "FY2026").mkdir(parents=True)
    (paths.data / "usgs_streamflow" / "FY2026").mkdir(parents=True)
    pd.DataFrame({"date": ["2026-02-28", "2026-03-01"], "PREC_DAILY": [0, 0]}).to_csv(paths.data / "snotel/FY2026/s.csv", index=False)
    pd.DataFrame({"datetime": ["2026-02-28 00:00:00+00:00"], "00060_Mean": [1]}).to_csv(paths.data / "usgs_streamflow/FY2026/u.csv", index=False)
    report = download.leakage_report(paths, date(2026, 3, 1))
    assert report == ["snotel/s.csv: rows on/after 2026-03-01"]
    assert download.leakage_report(paths, date(2026, 3, 2)) == []
