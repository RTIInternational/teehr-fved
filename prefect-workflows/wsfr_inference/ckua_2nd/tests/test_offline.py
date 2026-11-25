"""Offline tests (no network, no weights needed unless noted).

Network/regression tests live in test_regression.py and are opt-in (see that file).
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ckua_infer import build, monthly_flow, schema
from ckua_infer.paths import Paths


def test_core_matches_manifest():
    assert build.check_core() == []


def test_core_tamper_detected(tmp_path):
    (tmp_path / "solution.py").write_text("x")
    assert any(p.startswith("missing") for p in build.verify_manifest(tmp_path, build.CORE_MANIFEST))


def test_patches_apply_and_set_workers_to_zero(tmp_path):
    import shutil
    import subprocess

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    cfg = (tmp_path / "src/configs/forecast_cv_mlp_sumres_predict.yaml").read_text()
    assert "workers: 0" in cfg and "workers: 10" not in cfg


def test_multiscaler_loads_scalers_pickled_without_clip(tmp_path):
    """Scalers pickled by an older sklearn have no `clip` attribute; transform() must still work on newer sklearn."""
    import importlib.util
    import shutil
    import subprocess

    import numpy as np
    from joblib import dump
    from sklearn.preprocessing import MaxAbsScaler

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    spec = importlib.util.spec_from_file_location("multiscaler_patched", tmp_path / "src/libs/multiscaler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    scaler = MaxAbsScaler().fit([[50.0]])
    if hasattr(scaler, "clip"):
        del scaler.clip  # what an old pickle looks like after loading on new sklearn
    dump({"site": scaler}, tmp_path / "ms.pkl")
    ms = mod.MultiScaler.from_file(str(tmp_path / "ms.pkl"))
    assert ms.transform("site", np.array([25.0])) == pytest.approx([0.5])
    assert ms.inverse_transform("site", np.array([0.5])) == pytest.approx([25.0])


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
    from ckua_infer import download

    paths = Paths(tmp_path)
    (paths.data / "snotel" / "FY2026").mkdir(parents=True)
    (paths.data / "usgs_streamflow" / "FY2026").mkdir(parents=True)
    pd.DataFrame({"date": ["2026-02-28", "2026-03-01"], "PREC_DAILY": [0, 0]}).to_csv(paths.data / "snotel/FY2026/s.csv", index=False)
    pd.DataFrame({"datetime": ["2026-02-28 00:00:00+00:00"], "00060_Mean": [1]}).to_csv(paths.data / "usgs_streamflow/FY2026/u.csv", index=False)
    report = download.leakage_report(paths, date(2026, 3, 1))
    assert report == ["snotel/s.csv: rows on/after 2026-03-01"]
    assert download.leakage_report(paths, date(2026, 3, 2)) == []
