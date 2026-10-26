"""End-to-end test of ingest_gridded_data (references -> raw_data -> pyramids) on local repos.

Uses the UA SWANN source pointed at local netCDF files named like UA's, and the CU-SWE source pointed
at local GeoTIFFs named like CU's. Needs teehr and Prefect.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import zarr
from obstore.store import from_url
from pyproj import CRS

pytest.importorskip("teehr")
pytest.importorskip("h5netcdf")
icechunk = pytest.importorskip("icechunk")
rasterio = pytest.importorskip("rasterio")
from prefect.testing.utilities import prefect_test_harness  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

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


def _local_repo(tmp_path, src, monkeypatch):
    """A local repo reading virtual chunks from ``src``; patches the flows to use it and returns its opener."""
    prefix = f"file://{src}/"
    config = icechunk.RepositoryConfig.default()
    config.set_virtual_chunk_container(icechunk.VirtualChunkContainer(prefix, icechunk.local_filesystem_store(str(src))))
    storage = icechunk.local_filesystem_storage(str(tmp_path / "repo"))
    access = {prefix: icechunk.credentials.LocalFileSystemAccess}

    def open_repo(*_, **__):
        if icechunk.Repository.exists(storage):
            return icechunk.Repository.open(storage, config=config, authorize_virtual_chunk_access=access)
        return icechunk.Repository.create(storage, config=config, authorize_virtual_chunk_access=access)

    monkeypatch.setattr(ing.gu, "configure_icechunk_s3_repo", open_repo)
    monkeypatch.setattr(bp.gu, "build_icechunk_s3_storage", lambda **_: storage)
    monkeypatch.setattr(bp.gu, "open_repo_for_reading", open_repo)
    return open_repo


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

    monkeypatch.setattr(gs.UASwan4km, "source_bucket", prefix.rstrip("/"))
    monkeypatch.setattr(gs.UASwan4km, "list_files", list_files)
    return publish, _local_repo(tmp_path, src, monkeypatch)


# A small CU-SWE-like grid: NAD83, 0.05 degree pixels, 16 px tiles, CU's nodata value
TIFF_SHAPE = (32, 48)
TIFF_ORIGIN = (-110.0, 41.0)
TIFF_RES = 0.05
TIFF_NODATA = np.float32(3.4e38)


@pytest.fixture
def cu(tmp_path, monkeypatch):
    """CU-SWE source and repo on local storage; returns publish(day) -> the file's values in m (nodata as NaN) and an opener."""
    src = tmp_path / "src"
    (src / "NRT").mkdir(parents=True)
    rng = np.random.default_rng(0)

    def publish(day):
        values = rng.uniform(0, 3, TIFF_SHAPE).astype("float32")
        values[:5, :7] = TIFF_NODATA
        with rasterio.open(
            src / "NRT" / f"WW_phvrcn_{day:%Y%m%d}_fscamsk_clp.tif", "w", driver="GTiff",
            height=TIFF_SHAPE[0], width=TIFF_SHAPE[1], count=1, dtype="float32", crs="EPSG:4269",
            transform=from_origin(*TIFF_ORIGIN, TIFF_RES, TIFF_RES), nodata=TIFF_NODATA,
            tiled=True, blockxsize=16, blockysize=16, compress="lzw",
        ) as dst:
            dst.write(values, 1)
        return np.where(values == TIFF_NODATA, np.nan, values)

    # The real listing and preprocessing, over the local files and without keys
    monkeypatch.setattr(gs.CUSwe, "source_bucket", f"file://{src}")
    monkeypatch.setattr(gs.CUSwe, "store_kwargs", {})
    monkeypatch.setattr(gs.CUSwe, "credentials", lambda self: {})
    monkeypatch.setattr(gs, "_keyed_store", lambda source: from_url(f"{source.source_bucket}/"))
    return publish, _local_repo(tmp_path, src, monkeypatch)


def _run(start, end, mode="append"):
    ing.ingest_gridded_data(IngestGriddedDataInput(
        source={"type": "ua-swann-4km"}, start_dt=start, end_dt=end, write_mode=mode, fallback_source_crs="EPSG:4269",
        factors=[1, 2], dest_bucket="unused", base_prefix="unused", ignore_unreadable_file=False,
    ))


def _groups(open_repo):
    store = open_repo().readonly_session("main").store
    return {g: xr.open_zarr(store, group=g, consolidated=False) for g in GROUPS}


def test_grid_name_on_new_and_existing_repos(harness, ua):
    publish, open_repo = ua
    for d in DAYS[:10]:
        publish(d, "stable", d.dayofyear, "2026-01-01")
    _run("1981-10-01", "1981-10-05")
    assert ing.tg.read_grid_name(open_repo().readonly_session("main").store) == "ua_swann_4km"

    # A repo created before grid_name existed gains it on its next ingest
    session = open_repo().writable_session("main")
    del zarr.open_group(session.store, mode="a", zarr_format=3).attrs["grid_name"]
    session.commit("Drop grid_name")
    _run("1981-10-06", "1981-10-10")
    assert ing.tg.read_grid_name(open_repo().readonly_session("main").store) == "ua_swann_4km"


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
    cf_xarray = pytest.importorskip("cf_xarray")  # noqa: F841  # registers .cf, as xpublish-edr uses it
    for ds in g.values():
        assert ds.time.to_index().is_monotonic_increasing
        assert ds.cf.axes["T"] == ["time"]  # xpublish-edr selects datetime through it
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


def test_geotiff_values_match_source(harness, cu):
    publish, open_repo = cu
    days = pd.date_range("2026-03-01", periods=3, freq="D")
    expected = {d: publish(d) for d in days}
    ing.ingest_gridded_data(IngestGriddedDataInput(
        source={"type": "cu-swe"}, start_dt="2026-03-01", end_dt="2026-03-03", write_mode="upsert",
        parser_type="tiff", x_dim="x", y_dim="y", factors=[1], dest_bucket="unused", base_prefix="unused",
        ignore_unreadable_file=False,
    ))
    store = open_repo().readonly_session("main").store
    raw = xr.open_zarr(store, group="raw_data", consolidated=False)

    # Times come from the file names, starting the grid at the first file
    assert list(raw.time.to_index()) == list(days)
    assert (raw.status.values >= 0).all()
    assert zarr.open_group(store, mode="r", zarr_format=3).attrs["time_origin"] == "2026-03-01T00:00:00"
    # Pixel centres and CRS from the GeoTIFF tags
    x0, y0 = TIFF_ORIGIN
    np.testing.assert_allclose(raw.x.values, x0 + (np.arange(TIFF_SHAPE[1]) + 0.5) * TIFF_RES)
    np.testing.assert_allclose(raw.y.values, y0 - (np.arange(TIFF_SHAPE[0]) + 0.5) * TIFF_RES)
    assert CRS.from_wkt(raw.spatial_ref.attrs["crs_wkt"]).to_epsg() == 4269
    # /raw_data holds plain mm; /references keeps the source m and decodes to mm
    assert {k: raw.swe_daily_inst.attrs[k] for k in ("units", "source_units")} == {"units": "mm", "source_units": "m"}
    assert "scale_factor" not in raw.swe_daily_inst.encoding and raw.swe_daily_inst.dtype == "float32"
    refs = xr.open_zarr(store, group="references", consolidated=False)
    packed = xr.open_zarr(store, group="references", consolidated=False, mask_and_scale=False).swe_daily_inst
    assert packed.dtype == "float32" and packed.attrs["scale_factor"] == 1000
    for d in days:
        source_m = expected[d]
        source_mm = source_m * np.float32(1000)
        np.testing.assert_array_equal(raw.swe_daily_inst.sel(time=d).transpose("y", "x").values, source_mm)
        # Decoded with the JSON (float64) scale factor
        np.testing.assert_array_equal(refs.swe_daily_inst.sel(time=d).transpose("y", "x").values.astype("float32"), source_mm)
        stored_m = packed.sel(time=d).transpose("y", "x").values
        np.testing.assert_array_equal(np.where(stored_m == TIFF_NODATA, np.nan, stored_m), source_m)
    # Pyramids are packed from the mm values
    pyramid = xr.open_zarr(store, group="pyramids/0", consolidated=False).swe_daily_inst
    np.testing.assert_allclose(float(pyramid.isel(time=0).mean()), float(raw.swe_daily_inst.isel(time=0).mean()), rtol=0.05)


def test_unit_conversion_composes_with_source_packing():
    ds = xr.Dataset({
        "swe_daily_inst": ("x", np.arange(3, dtype="int16"), {"units": "m", "scale_factor": np.float32(0.01), "add_offset": np.float32(1)}),
        "other": ("x", np.zeros(3, "float32"), {"units": "m"}),
    })
    out = ing.gu.apply_unit_conversions(ds, ing.VARIABLE_UNITS, ing.UNIT_CONVERSIONS)
    swe = out.swe_daily_inst.attrs
    assert (swe["units"], swe["source_units"]) == ("mm", "m")
    assert swe["scale_factor"] == np.float32(10) and swe["add_offset"] == np.float32(1000)
    assert swe["scale_factor"].dtype == np.float32
    assert out.other.attrs == {"units": "m"}  # not in VARIABLE_UNITS
    with pytest.raises(ValueError, match="No conversion"):
        ing.gu.apply_unit_conversions(xr.Dataset({"swe_daily_inst": ("x", [1.0], {"units": "ft"})}), ing.VARIABLE_UNITS, ing.UNIT_CONVERSIONS)
