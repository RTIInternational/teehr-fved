"""End-to-end test of ingest_gridded_data (references -> raw_data -> pyramids) on local repos.

Uses the UA SWANN source pointed at local netCDF files named like UA's. Needs teehr and Prefect.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import zarr

pytest.importorskip("teehr")
pytest.importorskip("h5netcdf")
icechunk = pytest.importorskip("icechunk")
from prefect.testing.utilities import prefect_test_harness  # noqa: E402

import build_geozarr_pyramids as bp  # noqa: E402
import ingest_gridded_data as ing  # noqa: E402
from workflows.models import gridded_sources as gs  # noqa: E402
from workflows.models.ingest_gridded_data_input import IngestGriddedDataInput  # noqa: E402

ORIGIN = pd.Timestamp("1981-10-01")
DAYS = pd.date_range(ORIGIN, periods=90, freq="D")
GROUPS = ("references", "raw_data", "pyramids/0", "pyramids/1")


@pytest.fixture(scope="module")
def harness():
    with prefect_test_harness():
        yield


@pytest.fixture
def ua(tmp_path, monkeypatch):
    """UA source and repo on local storage; returns publish(day, status, value, modified) and an opener."""
    src = tmp_path / "src"
    src.mkdir()
    prefix = f"file://{src}/"
    published = {}

    def publish(day, status, value, modified):
        for old in src.glob(f"*_{day:%Y%m%d}_*.nc"):
            old.unlink()
        name = f"UA_SWE_Depth_4km_v1_{day:%Y%m%d}_{status}.nc"
        xr.Dataset(
            {v: (("time", "lat", "lon"), np.full((1, 40, 50), value, "float32"), {"units": "millimeters h20"})
             for v in ("SWE", "DEPTH")},
            coords={"time": [day], "lat": np.linspace(40.0, 41.0, 40), "lon": np.linspace(-110.0, -108.0, 50)},
        ).to_netcdf(src / name, engine="h5netcdf")
        published[day] = {"time": day, "url": f"{prefix}{name}", "status": status, "last_modified": pd.Timestamp(modified)}

    def list_files(self, start_dt, end_dt):
        return gs._listing([r for d, r in published.items() if start_dt.date() <= d.date() <= end_dt.date()])

    config = icechunk.RepositoryConfig.default()
    config.set_virtual_chunk_container(icechunk.VirtualChunkContainer(prefix, icechunk.local_filesystem_store(str(src))))
    storage = icechunk.local_filesystem_storage(str(tmp_path / "repo"))
    access = {prefix: icechunk.credentials.LocalFileSystemAccess}

    def open_repo(*_, **__):
        if icechunk.Repository.exists(storage):
            return icechunk.Repository.open(storage, config=config, authorize_virtual_chunk_access=access)
        return icechunk.Repository.create(storage, config=config, authorize_virtual_chunk_access=access)

    monkeypatch.setattr(gs.UASwan4km, "source_bucket", prefix.rstrip("/"))
    monkeypatch.setattr(gs.UASwan4km, "list_files", list_files)
    monkeypatch.setattr(ing.gu, "configure_icechunk_s3_repo", open_repo)
    monkeypatch.setattr(bp.gu, "build_icechunk_s3_storage", lambda **_: storage)
    monkeypatch.setattr(bp.gu, "open_repo_for_reading", open_repo)
    return publish, open_repo


def _run(start, end, mode="append"):
    ing.ingest_gridded_data(IngestGriddedDataInput(
        source={"type": "ua-swann-4km"}, start_dt=start, end_dt=end, write_mode=mode, fallback_source_crs="EPSG:4269",
        factors=[1, 2], dest_bucket="unused", base_prefix="unused", ignore_unreadable_file=False,
    ))


def _groups(open_repo):
    store = open_repo().readonly_session("main").store
    return {g: xr.open_zarr(store, group=g, consolidated=False) for g in GROUPS}


def test_backfill_in_any_order_then_upsert(harness, ua):
    publish, open_repo = ua
    for d in DAYS:
        publish(d, "stable", d.dayofyear, "2026-01-01")
    for d in DAYS[70:]:
        publish(d, "provisional", 1000 + d.dayofyear, "2026-03-01")

    _run("1981-11-20", "1981-11-29")  # a later block first
    _run("1981-10-03", "1981-10-12")  # then an earlier one
    g = _groups(open_repo)
    expected = list(range(2, 12)) + list(range(50, 60))
    for ds in g.values():
        assert ds.time.to_index().is_monotonic_increasing
        assert list(np.flatnonzero(ds.status.values >= 0)) == expected
    raw = g["raw_data"]
    for i in expected:
        assert float(raw.swe_daily_inst.isel(time=i, lat=3, lon=4)) == DAYS[i].dayofyear
    assert abs(float(g["pyramids/0"].swe_daily_inst.isel(time=55).max()) - DAYS[55].dayofyear) < 0.2
    assert np.isnan(float(g["pyramids/0"].swe_daily_inst.isel(time=30).max()))  # unwritten slots are missing, not 0

    before = {k: v.updated_at.values.copy() for k, v in g.items()}
    _run("1981-10-03", "1981-11-29")  # nothing new
    after = _groups(open_repo)
    for k in GROUPS:
        assert ((after[k].updated_at.values == before[k]) | np.isnat(before[k])).all()

    _run("1981-12-10", "1981-12-19")  # provisional days, past the end of the axis
    raw = _groups(open_repo)["raw_data"]
    assert raw.sizes["time"] == 80 and raw.status.values[70] == 1
    created = raw.created_at.values[70]

    for d in DAYS[70:75]:
        publish(d, "stable", d.dayofyear, "2026-05-01")  # UA finalizes five days
    _run("1981-12-10", "1981-12-19", mode="append")
    assert _groups(open_repo)["raw_data"].status.values[70] == 1  # append leaves them
    _run("1981-12-10", "1981-12-19", mode="upsert")
    g = _groups(open_repo)
    for k in GROUPS:
        assert list(g[k].status.values[70:80]) == [2] * 5 + [1] * 5
    raw = g["raw_data"]
    assert float(raw.swe_daily_inst.isel(time=71, lat=0, lon=0)) == DAYS[71].dayofyear
    assert float(raw.swe_daily_inst.isel(time=76, lat=0, lon=0)) == 1000 + DAYS[76].dayofyear
    assert raw.created_at.values[70] == created and raw.updated_at.values[70] > created

    root = zarr.open_group(open_repo().readonly_session("main").store, mode="r", zarr_format=3).attrs
    assert {k: root[k] for k in ("append_dim", "time_origin", "configuration_name", "timeseries_type", "data_group")} == {
        "append_dim": "time", "time_origin": "1981-10-01T00:00:00", "configuration_name": "ua_swann_4km",
        "timeseries_type": "primary", "data_group": "/raw_data",
    }
