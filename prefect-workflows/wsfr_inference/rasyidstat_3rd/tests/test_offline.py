"""Offline tests (no network; the asset test needs fetched weights and is skipped otherwise)."""

import json
from datetime import date

import pandas as pd
import pytest

from rasyidstat_infer import build, download, monthly_flow, schema, solution
from rasyidstat_infer.paths import MODEL_VERSION, Paths


def test_core_matches_manifest():
    assert build.check_core() == []


def test_core_tamper_detected(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text("x")
    assert any(p.startswith("missing") for p in build.verify_manifest(tmp_path, build.CORE_MANIFEST))


def test_no_patches():
    # every deviation from the competition code must be a reviewable patch; this is the complete list
    assert [p.name for p in sorted(build.PATCHES.glob("*.patch"))] == ["001-no-ipython-import.patch", "002-numpy2-nan.patch"]


def test_patched_core_has_no_removed_numpy_aliases(tmp_path):
    import re
    import shutil
    import subprocess

    shutil.copytree(build.CORE, tmp_path / "src")
    for patch in sorted(build.PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "-d", str(tmp_path / "src"), "-i", str(patch)], check=True, capture_output=True)
    removed = re.compile(r"\bnp\.(NaN|NAN|Inf|Infinity|float_|complex_|product|cumproduct|in1d|row_stack)\b")
    hits = [f"{f.name}:{i}" for f in (tmp_path / "src").rglob("*.py") for i, line in enumerate(f.read_text().splitlines(), 1) if removed.search(line)]
    assert hits == []


def test_assets_checksums_if_present():
    paths = Paths.from_root()
    if not paths.assets.is_dir():
        pytest.skip("assets not fetched")
    assert build.check_assets(paths) == []


def test_forecast_year_and_complete_months():
    assert monthly_flow.expected_months(date(2026, 3, 1)) == [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    assert not monthly_flow._month_ended(2026, 3, date(2026, 3, 31))


def test_schema_validation_and_version():
    row = dict(site_id="a", issue_date="2026-03-01", volume_10=1.0, volume_50=2.0, volume_90=3.0)
    ok = schema.to_frame([row])
    assert schema.validate(ok) == [] and list(ok.columns) == schema.COLUMNS
    assert "quantiles not ordered" in schema.validate(ok.assign(volume_10=5.0))
    assert schema.to_frame([row], "v_partial")["model_version"].iloc[0] == "v_partial"


def test_issue_date_season():
    download.check_issue_date(date(2026, 7, 1))
    with pytest.raises(ValueError):
        download.check_issue_date(date(2026, 8, 1))


def test_partial_ensemble_is_labelled():
    from rasyidstat_infer import engine

    assert solution.model_version(engine.ALL_VARIANTS) == MODEL_VERSION
    assert solution.model_version(["base_swe", "swe_ua"]) == f"{MODEL_VERSION}_partial2of9"


def test_source_report_flags_stale_inputs():
    last = {k: pd.Timestamp("2026-02-28") for k in solution.DAILY_SOURCES}
    assert solution.source_report(last, date(2026, 3, 1)) == []
    last["uaswann_basin"] = pd.Timestamp("2026-02-20")
    del last["cdec"]
    report = solution.source_report(last, date(2026, 3, 1))
    assert len(report) == 2 and any("uaswann_basin" in r for r in report) and any("cdec: no data" in r for r in report)


def test_leakage_report_flags_future_rows(tmp_path):
    paths = Paths(tmp_path)
    (paths.downloads / "snotel" / "FY2026").mkdir(parents=True)
    (paths.downloads / "usgs_streamflow" / "FY2026").mkdir(parents=True)
    pd.DataFrame({"date": ["2026-02-28", "2026-03-01", "2026-03-02"], "PREC_DAILY": [0, 0, 0]}).to_csv(paths.downloads / "snotel/FY2026/s.csv", index=False)
    pd.DataFrame({"datetime": ["2026-02-28 00:00:00+00:00"], "00060_Mean": [1]}).to_csv(paths.downloads / "usgs_streamflow/FY2026/u.csv", index=False)
    assert download.leakage_report(paths, date(2026, 3, 1)) == ["snotel/s.csv: rows after 2026-03-01"]
    assert download.leakage_report(paths, date(2026, 3, 2)) == []  # the issue day's own row is allowed


class _Resp:
    def __init__(self, status=200, content=b"CDF\x01data", text=""):
        self.status_code, self.content, self.text = status, content, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_swann_tier_fallback_and_upgrade(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    available = {"early"}  # what the server holds for every day
    calls = []

    def fake_get(url, **kw):
        tier = url.rsplit("_", 1)[1][:-3]
        calls.append(tier)
        return _Resp(200 if tier in available else 404)

    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download, "_fy_start", lambda d: date(2026, 1, 1))  # three days instead of a whole water year
    issue = date(2026, 1, 4)
    assert download.swann_daily(paths, issue, workers=1) == []
    tiers = json.loads((paths.downloads / "uaswann/raw/daily_tiers.json").read_text())
    assert tiers == {"20260101": "early", "20260102": "early", "20260103": "early"}

    # nothing better yet: only the better tiers are requested again, nothing is downgraded
    calls.clear()
    download.swann_daily(paths, issue, workers=1)
    assert set(calls) == {"stable", "provisional"}

    available.add("stable")
    download.swann_daily(paths, issue, workers=1)
    assert set(json.loads((paths.downloads / "uaswann/raw/daily_tiers.json").read_text()).values()) == {"stable"}


def test_swann_missing_days_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(download.requests, "get", lambda url, **kw: _Resp(404))
    monkeypatch.setattr(download, "_fy_start", lambda d: date(2026, 1, 1))
    warnings = download.swann_daily(Paths(tmp_path), date(2026, 1, 3), workers=1)
    assert len(warnings) == 1 and "2 of 2 days unavailable" in warnings[0]


def test_swann_huc_converted_to_legacy_columns(tmp_path, monkeypatch):
    body = (
        "# dataset: National SnowView watershed daily summary\n# missing_value: blank\n"
        "date,water_year,overall_cumulative_precip_in,overall_mean_swe_in,overall_snow_covered_area_sq_mi\n"
        "2026-02-27,2026,12.5,3.25,100.0\n2026-02-28,2026,12.75,3.5,101.0\n"
    )
    urls = []
    monkeypatch.setattr(download.requests, "get", lambda url, **kw: urls.append(url) or _Resp(text=body))
    assert download.swann_huc(Paths(tmp_path), date(2026, 3, 1)) == []
    assert all(u.startswith("https://snowview.arizona.edu/csv/Download/Watersheds/") for u in urls)
    f = next((tmp_path / "downloads/uaswann/raw/huc6").glob("*.csv"))
    df = pd.read_csv(f)
    assert list(df.columns) == ["Date", "Average SWE (in)", "Average Accumulated Water Year PPT (in)"]
    assert df["Average SWE (in)"].tolist() == [3.25, 3.5]


def test_predict_does_not_rebuild_existing_build(tmp_path, monkeypatch):
    # rebuilding deletes build/src, which is the working directory of the already bootstrapped engine (`run` = download, preprocess, predict)
    from rasyidstat_infer import cli

    paths = Paths(tmp_path)
    paths.src.mkdir(parents=True)
    monkeypatch.setattr(cli.build_mod, "build", lambda p: pytest.fail("build() must not run when build/src exists"))
    monkeypatch.setattr(solution, "predict", lambda *a, **k: (pd.DataFrame(), [], []))
    monkeypatch.setattr(cli.schema, "validate", lambda df: [])
    cli.cmd_predict(paths, date(2026, 3, 1), None, tmp_path / "o.csv", True, False)
