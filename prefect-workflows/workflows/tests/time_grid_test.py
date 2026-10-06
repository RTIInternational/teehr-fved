"""Tests for the fixed time grid (utils/time_grid.py) on local IceChunk repos."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr
import zarr

pytest.importorskip("h5netcdf")
icechunk = pytest.importorskip("icechunk")
from obspec_utils.registry import ObjectStoreRegistry  # noqa: E402
from obstore.store import LocalStore  # noqa: E402
from virtualizarr import open_virtual_dataset  # noqa: E402
from virtualizarr.parsers import HDFParser  # noqa: E402

from utils import time_grid as tg  # noqa: E402

ORIGIN, STEP, DIM = pd.Timestamp("1981-10-01"), pd.Timedelta("1D"), "time"
DAYS = pd.date_range(ORIGIN, periods=70, freq="D")
MODIFIED = np.datetime64("2026-01-01", "ms")


@pytest.fixture
def source(tmp_path):
    """One small netCDF file per day, value = day of year, and a virtual reader for them."""
    src = tmp_path / "src"
    src.mkdir()
    for d in DAYS:
        xr.Dataset(
            {"SWE": (("time", "lat", "lon"), np.full((1, 6, 8), d.dayofyear, "float32"))},
            coords={"time": [d], "lat": np.arange(6.0), "lon": np.arange(8.0)},
        ).to_netcdf(src / f"f_{d:%Y%m%d}.nc", engine="h5netcdf")
    prefix = f"file://{src}/"
    registry = ObjectStoreRegistry({prefix: LocalStore(str(src))})

    def open_days(days):
        parts = [
            open_virtual_dataset(f"{prefix}f_{d:%Y%m%d}.nc", registry=registry, parser=HDFParser(),
                                 loadable_variables=["time", "lat", "lon"])
            for d in days
        ]
        return xr.concat(parts, dim=DIM, coords="minimal", compat="override", combine_attrs="override")

    return prefix, src, open_days


@pytest.fixture
def repo(tmp_path, source):
    prefix, src, _ = source
    config = icechunk.RepositoryConfig.default()
    config.set_virtual_chunk_container(icechunk.VirtualChunkContainer(prefix, icechunk.local_filesystem_store(str(src))))
    return icechunk.Repository.create(
        icechunk.local_filesystem_storage(str(tmp_path / "repo")), config=config, authorize_virtual_chunk_access={prefix: icechunk.credentials.LocalFileSystemAccess}
    )


def _write_refs(repo, ds, status, end=None):
    """Write virtual refs for ``ds`` into /references, creating it on the first call."""
    session = repo.writable_session("main")
    stored = tg.read_step_metadata(session.store, "references", DIM)
    if stored is None:
        tg.create_group(session, "references", ds, ORIGIN, STEP, DIM, end or ds[DIM].to_index()[-1], virtual=True)
        stored = tg.read_step_metadata(session.store, "references", DIM)
    else:
        tg.ensure_axis(session, "references", ds[DIM].to_index()[-1], STEP, DIM)
    n = ds.sizes[DIM]
    ds = tg.with_step_metadata(ds, DIM, [status] * n, np.full(n, MODIFIED), tg.utc_now(), stored)
    tg.region_write(session, "references", ds, DIM, virtual=True)
    session.commit("refs")


def _refs(repo):
    return xr.open_zarr(repo.readonly_session("main").store, group="references", consolidated=False)


def test_create_group_stores_nothing(repo, source):
    _, _, open_days = source
    session = repo.writable_session("main")
    tg.create_group(session, "references", open_days(DAYS[40:42]), ORIGIN, STEP, DIM, DAYS[49], virtual=True)
    meta = tg.read_step_metadata(session.store, "references", DIM)
    assert len(meta) == 50 and meta.index[0] == ORIGIN
    assert (meta.status == tg.UNWRITTEN).all() and meta.updated_at.isna().all()


def test_out_of_order_writes_land_in_their_slots(repo, source):
    _, _, open_days = source
    _write_refs(repo, open_days(DAYS[40:50]), 2)
    _write_refs(repo, open_days(DAYS[5:12]), 1)
    refs = _refs(repo)
    written = np.flatnonzero(refs.status.values >= 0)
    assert list(written) == list(range(5, 12)) + list(range(40, 50))
    assert refs.time.to_index().is_monotonic_increasing
    for i in written:
        assert float(refs.SWE.isel(time=i, lat=0, lon=0)) == DAYS[i].dayofyear
    assert np.isnan(float(refs.SWE.isel(time=20, lat=0, lon=0)))


def test_axis_grows_and_new_slots_are_unwritten(repo, source):
    _, _, open_days = source
    _write_refs(repo, open_days(DAYS[0:5]), 2)
    _write_refs(repo, open_days(DAYS[60:65]), 0)
    refs = _refs(repo)
    assert refs.sizes["time"] == 65
    assert refs.status.values[30] == tg.UNWRITTEN and float(refs.SWE.isel(time=62, lat=1, lon=1)) == DAYS[62].dayofyear


def test_select_source_steps(repo, source):
    _, _, open_days = source
    _write_refs(repo, open_days(DAYS[5:7]), 1)
    _write_refs(repo, open_days(DAYS[60:61]), 0)
    stored = tg.read_step_metadata(repo.readonly_session("main").store, "references", DIM)
    listing = pd.DataFrame(
        {"status": ["stable", "provisional", "stable", "early"],
         "last_modified": pd.to_datetime(["2026-01-01", "2026-06-01", "2026-01-01", "2026-01-01"])},
        index=pd.DatetimeIndex([DAYS[5], DAYS[6], DAYS[20], DAYS[60]], name=DIM),
    )
    assert list(tg.select_source_steps(listing, stored, "append").index) == [DAYS[20]]
    # DAYS[5] became more final, DAYS[6] was re-issued, DAYS[20] is new, DAYS[60] is unchanged
    assert list(tg.select_source_steps(listing, stored, "upsert").index) == [DAYS[5], DAYS[6], DAYS[20]]


def test_materialize_propagates_only_stale_steps_and_keeps_created_at(repo, source):
    _, _, open_days = source
    _write_refs(repo, open_days(DAYS[40:50]), 2)
    store = repo.readonly_session("main").store
    refs_meta = tg.read_step_metadata(store, "references", DIM)
    refs = xr.open_zarr(store, group="references", consolidated=False, chunks=None).drop_vars(list(tg.STEP_COORDS))

    def materialize():
        session = repo.writable_session("main")
        src = tg.read_step_metadata(session.store, "references", DIM)
        dst = tg.read_step_metadata(session.store, "raw_data", DIM)
        stale = tg.stale_steps(src, dst)
        if len(stale) == 0:
            return stale
        if dst is None:
            tg.create_group(session, "raw_data", refs, ORIGIN, STEP, DIM, src.index[-1],
                            encoding={"SWE": {"chunks": (1, 4, 4), "shards": (10, 4, 4)}})
            dst = tg.read_step_metadata(session.store, "raw_data", DIM)
        for batch in tg.shard_batches(stale, src.index, 10):
            m = src.loc[batch]
            part = tg.with_step_metadata(refs.sel({DIM: batch}).load(), DIM, m.status.to_numpy(),
                                         m.source_last_modified.to_numpy(), m.updated_at.to_numpy(), dst)
            tg.region_write(session, "raw_data", part, DIM)
        session.commit("materialize")
        return stale

    assert len(materialize()) == 10
    assert len(materialize()) == 0
    raw = xr.open_zarr(repo.readonly_session("main").store, group="raw_data", consolidated=False)
    created = raw.created_at.values[45]
    _write_refs(repo, open_days(DAYS[45:46]), 2)
    assert list(materialize()) == [DAYS[45]]
    raw = xr.open_zarr(repo.readonly_session("main").store, group="raw_data", consolidated=False)
    assert raw.created_at.values[45] == created and raw.updated_at.values[45] > created
    assert refs_meta.index[0] == ORIGIN


def test_stored_encoding(repo, source):
    _, _, open_days = source
    _write_refs(repo, open_days(DAYS[3:4]), 2)
    g = zarr.open_group(repo.readonly_session("main").store, path="references", mode="r", zarr_format=3)
    audit = g["updated_at"]
    assert audit.attrs["units"] == "milliseconds since 1970-01-01" and audit.attrs["_FillValue"] == np.iinfo("int64").min
    assert audit.dtype == np.int64 and g["status"].dtype == np.int8
    assert g["time"].attrs["units"].startswith("days since 1981-10-01")
    assert _refs(repo).created_at.isnull().values[0]


def test_grid_attrs_and_off_grid_timestamps(repo):
    session = repo.writable_session("main")
    tg.write_grid_attrs(session.store, {"append_dim": DIM, "time_origin": ORIGIN.isoformat(), "time_step": STEP.isoformat()})
    assert tg.read_grid(session.store) == (DIM, ORIGIN, STEP)
    tg.check_on_grid(pd.DatetimeIndex([ORIGIN, ORIGIN + 3 * STEP]), ORIGIN, STEP)
    with pytest.raises(ValueError):
        tg.check_on_grid(pd.DatetimeIndex(["1981-10-05T12:00"]), ORIGIN, STEP)
    with pytest.raises(ValueError):
        tg.check_on_grid(pd.DatetimeIndex(["1981-09-30"]), ORIGIN, STEP)


class _FakeSource:
    """Listing for DAYS, as a GriddedSource returns it."""

    time_step = STEP

    def __init__(self, days=DAYS):
        self.days = days

    def time_origin(self):
        return ORIGIN

    def list_files(self, start, end):
        days = self.days[(self.days >= pd.Timestamp(start)) & (self.days <= pd.Timestamp(end))]
        return pd.DataFrame({"url": "", "status": "stable", "last_modified": pd.Timestamp("2025-12-23")},
                            index=pd.DatetimeIndex(days, name=DIM))


def _legacy_repo(tmp_path, days):
    """A repo written the old way: appended steps, xarray's default encodings, status only."""
    repo = icechunk.Repository.create(icechunk.local_filesystem_storage(str(tmp_path / "legacy")))
    for i, chunk in enumerate((days[:10], days[10:])):
        session = repo.writable_session("main")
        for group in ("raw_data", "pyramids/0"):
            ds = xr.Dataset({"swe": (("time", "y", "x"), np.stack([np.full((4, 4), d.dayofyear, "float32") for d in chunk]))},
                            coords={"time": chunk, "status": ("time", np.full(len(chunk), 2, "int8"))})
            ds.to_zarr(session.store, group=group, mode="w" if i == 0 else "a", append_dim=None if i == 0 else "time",
                       zarr_format=3, consolidated=False)
        session.commit(f"legacy {i}")
    return repo


def test_migrate_legacy_repo_in_place(tmp_path):
    days = DAYS[:25].delete(12)  # a gap, as at the source
    repo = _legacy_repo(tmp_path, days)
    before = xr.open_zarr(repo.readonly_session("main").store, group="raw_data", consolidated=False).swe.values

    report = tg.migrate_repo(repo, _FakeSource(days), "legacy_repo")
    assert not report["migrated"] and report["problems"] == []
    assert tg.read_grid(repo.readonly_session("main").store) is None  # dry run wrote nothing

    report = tg.migrate_repo(repo, _FakeSource(days), "legacy_repo", dry_run=False)
    assert report["migrated"] and report["groups"]["/raw_data"]["gaps"] == 1
    store = repo.readonly_session("main").store
    assert tg.read_grid(store) == (DIM, ORIGIN, STEP)
    raw = xr.open_zarr(store, group="raw_data", consolidated=False)
    assert np.array_equal(raw.swe.values, before)  # data untouched
    metas = {g: tg.read_step_metadata(store, g, DIM) for g in ("raw_data", "pyramids/0")}
    assert len(tg.stale_steps(metas["raw_data"], metas["pyramids/0"])) == 0  # nothing reprocesses
    assert metas["raw_data"].source_last_modified.notna().all()

    # The migrated repo takes new writes: past its end and into its gap's neighbourhood
    session = repo.writable_session("main")
    tg.ensure_axis(session, "raw_data", DAYS[30], STEP, DIM)
    new = xr.Dataset({"swe": (("time", "y", "x"), np.full((1, 4, 4), 99.0, "float32"))}, coords={"time": [DAYS[30]]})
    new = tg.with_step_metadata(new, DIM, [2], [MODIFIED], tg.utc_now(), tg.read_step_metadata(session.store, "raw_data", DIM))
    tg.region_write(session, "raw_data", new, DIM)
    session.commit("new step")
    raw = xr.open_zarr(repo.readonly_session("main").store, group="raw_data", consolidated=False)
    assert float(raw.swe.sel(time=DAYS[30]).max()) == 99.0 and raw.time.to_index().is_monotonic_increasing

    assert tg.migrate_repo(repo, _FakeSource(days), "legacy_repo", dry_run=False)["migrated"] is False  # idempotent


def test_migrate_refuses_unsafe_repos(tmp_path):
    shuffled = DAYS[10:20].append(DAYS[:10])  # backfilled earlier days after later ones
    report = tg.migrate_repo(_legacy_repo(tmp_path / "a", shuffled), _FakeSource(), "r", dry_run=False)
    assert not report["migrated"] and any("not sorted" in p for p in report["problems"])
    late_start = DAYS[5:20]  # the source has earlier days the axis can't take
    report = tg.migrate_repo(_legacy_repo(tmp_path / "b", late_start), _FakeSource(), "r", dry_run=False)
    assert not report["migrated"] and any("record starts" in p for p in report["problems"])
