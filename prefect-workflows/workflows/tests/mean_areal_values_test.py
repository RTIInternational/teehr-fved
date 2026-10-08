"""Tests for selecting grid steps in the mean areal values flow. Needs teehr and pyspark."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

pytest.importorskip("teehr")
pytest.importorskip("pyspark")
from mean_areal_values import _written_steps  # noqa: E402
from workflows.models.mean_areal_inputs import MeanArealValuesInput  # noqa: E402

TIMES = pd.date_range("2000-01-01", periods=6, freq="D")


def _args(**kwargs):
    return MeanArealValuesInput(
        configuration_name="c", temp_dir_path="/tmp", location_id_prefix="p", grid_variable_name="v",
        domain_name="d", dest_bucket="b", base_prefix="p", **kwargs,
    )


def _grid(status):
    return xr.DataArray(np.arange(6.0), dims="time", coords={"time": TIMES, "status": ("time", np.array(status, "int8"))})


def test_skips_unwritten_slots():
    da = _written_steps(_grid([2, -1, 2, 1, -1, 0]), _args())
    assert list(da.time.values) == list(TIMES[[0, 2, 3, 5]].values)


def test_window():
    da = _written_steps(_grid([2] * 6), _args(start_dt="2000-01-02", end_dt="2000-01-04"))
    assert list(da.time.values) == list(TIMES[1:4].values)


def test_repo_without_status_keeps_all_steps():
    da = xr.DataArray(np.arange(6.0), dims="time", coords={"time": TIMES})
    assert da.equals(_written_steps(da, _args()))


def test_defaults_to_upsert():
    assert _args().write_mode == "upsert"
