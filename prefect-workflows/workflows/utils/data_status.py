"""Per-timestep data status, stored as a CF ``status_flag`` ancillary variable."""
import numpy as np
import xarray as xr

STATUS_COORD = "status"
# Ordered worst to best, so a higher flag value is a more final version
STATUS_MEANINGS = ["early", "provisional", "stable"]


def with_status(ds: xr.Dataset, status: str, dim: str = "time") -> xr.Dataset:
    """Flag every step of ``ds`` along ``dim`` with ``status``, linked from each data variable."""
    flag = xr.DataArray(
        np.full(ds.sizes[dim], STATUS_MEANINGS.index(status), dtype="int8"),
        dims=dim,
        attrs={
            "standard_name": "status_flag",
            "long_name": "data status",
            "flag_values": np.arange(len(STATUS_MEANINGS), dtype="int8"),
            "flag_meanings": " ".join(STATUS_MEANINGS),
        },
    )
    ds = ds.assign_coords({STATUS_COORD: flag})
    for var in ds.data_vars:
        if dim in ds[var].dims:
            ds[var].attrs["ancillary_variables"] = STATUS_COORD
    return ds
