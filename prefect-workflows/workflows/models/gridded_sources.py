"""Gridded data sources for the ingest_gridded_data Prefect flow, selected by their ``type``."""
import os
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Annotated, ClassVar, Literal, Union

import pandas as pd
import requests
import xarray as xr
from prefect.blocks.system import Secret
from pydantic import BaseModel, Field, field_validator
from teehr.fetching.utils import REMOTE_RETRY_CONFIG

from workflows.utils.data_status import STATUS_MEANINGS, with_status


class GriddedSource(BaseModel, ABC):
    """A gridded source: its files and its IceChunk repository."""

    source_bucket: ClassVar[str]
    # Source-specific obstore kwargs; deployment obstore_kwargs override them
    store_kwargs: ClassVar[dict] = {}
    # Options for the IceChunk virtual chunk container's object store, e.g. region
    virtual_store_kwargs: ClassVar[dict] = {}

    @abstractmethod
    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]: ...

    @abstractmethod
    def repository_name(self) -> str:
        """IceChunk repository (configuration) name."""

    @abstractmethod
    def ingest_variables(self) -> list[str]:
        """Source variables to materialize."""

    def credentials(self) -> dict:
        """Source access keys, for obstore and the virtual chunk container; empty means anonymous.

        Both take the same dict, so use keys they share: S3 ``access_key_id``, ``secret_access_key``,
        ``session_token``; GCS ``service_account_key``, ``application_credentials``, ``bearer_token``.
        Keys are read once per run, so they must outlive it.
        """
        return {}

    def preprocess(self, ds: xr.Dataset, url: str) -> xr.Dataset:
        """Adjust one file's virtual dataset before concatenation."""
        return ds


def _water_year(dt: date) -> int:
    """Water years start October 1."""
    return dt.year + 1 if dt.month >= 10 else dt.year


class UASwan4km(GriddedSource):
    type: Literal["ua-swann-4km"] = "ua-swann-4km"
    # Variants that may be used; each day takes the most final one published
    status: list[str] = ["stable", "provisional", "early"]
    variables: list[str] = ["SWE", "DEPTH"]

    source_bucket: ClassVar[str] = "https://climate.arizona.edu"
    base_url: ClassVar[str] = "https://climate.arizona.edu/data/UA_SWE/DailyData_4km"
    file_pattern: ClassVar[re.Pattern] = re.compile(r"UA_SWE_Depth_4km_v1_(\d{8})_(early|provisional|stable)\.nc")

    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]:
        """List one file per day in the range: the most final allowed variant in each water year's directory."""
        start, end = start_dt.date(), end_dt.date()
        best: dict[date, str] = {}
        for wy in range(_water_year(start), _water_year(end) + 1):
            resp = requests.get(f"{self.base_url}/WY{wy}/", timeout=60)
            if resp.status_code == 404:  # water year not published yet
                continue
            resp.raise_for_status()
            for stamp, status in self.file_pattern.findall(resp.text):
                day = datetime.strptime(stamp, "%Y%m%d").date()
                if status not in self.status or not start <= day <= end:
                    continue
                if day not in best or STATUS_MEANINGS.index(status) > STATUS_MEANINGS.index(best[day]):
                    best[day] = status
        return [
            f"{self.base_url}/WY{_water_year(day)}/UA_SWE_Depth_4km_v1_{day:%Y%m%d}_{status}.nc"
            for day, status in sorted(best.items())
        ]

    def repository_name(self) -> str:
        return "ua-swann-4km"

    def ingest_variables(self) -> list[str]:
        return list(self.variables)

    def preprocess(self, ds: xr.Dataset, url: str) -> xr.Dataset:
        return with_status(ds, url.rsplit("_", 1)[-1].removesuffix(".nc"))


class ISnobal(GriddedSource):
    """iSnobal model output from M3Works, one daily GeoTIFF per variable."""

    type: Literal["isnobal"] = "isnobal"
    domain: str = Field(..., description="Model domain, e.g. 'boise'. Each domain has its own repository.")
    variable: str = Field(default="specific_mass", description="File name prefix of the variable to ingest")
    prefix: str = Field(default="nrcs/shared", description="Key prefix above the domain directories")
    status: str = Field(default="stable", description=f"Data status recorded for every step: one of {STATUS_MEANINGS}")

    source_bucket: ClassVar[str] = "s3://m3w-transfer"
    store_kwargs: ClassVar[dict] = {"region": "us-west-2", "retry_config": REMOTE_RETRY_CONFIG}
    virtual_store_kwargs: ClassVar[dict] = {"region": "us-west-2"}
    # Units per variable; only some files carry a units tag
    units: ClassVar[dict] = {"specific_mass": "kg m-2"}

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in STATUS_MEANINGS:
            raise ValueError(f"status must be one of {STATUS_MEANINGS}, got '{v}'")
        return v

    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]:
        """Build one file URL per day, laid out as <domain>/wy<YYYY>/run<YYYYMMDD>/<variable>_<time>.tif."""
        return [
            f"{self.source_bucket}/{self.prefix}/{self.domain}/wy{_water_year(day)}/"
            f"run{day:%Y%m%d}/{self.variable}_{day:%Y-%m-%d}T23:00:00.tif"
            for day in pd.date_range(start_dt.date(), end_dt.date(), freq="D")
        ]

    def repository_name(self) -> str:
        return f"isnobal_{self.domain}"

    def ingest_variables(self) -> list[str]:
        return [self.variable]

    def credentials(self) -> dict:
        # Env vars (e.g. set in a notebook) take precedence over the Prefect Secret blocks
        blocks = {"access_key_id": "m3works-aws-access-key-id", "secret_access_key": "m3works-aws-secret-access-key"}
        return {
            key: os.environ.get(block.upper().replace("-", "_")) or Secret.load(block).get()
            for key, block in blocks.items()
        }

    def preprocess(self, ds: xr.Dataset, url: str) -> xr.Dataset:
        # Parsed with IFD 0 (full resolution), the only variable is "0"
        time = pd.Timestamp(url.rsplit("_", 1)[-1].removesuffix(".tif"))
        ds = ds.rename({"0": self.variable}).expand_dims(time=[time])
        if self.variable in self.units:
            ds[self.variable].attrs.setdefault("units", self.units[self.variable])
        return with_status(ds, self.status)


GriddedSourceType = Annotated[Union[UASwan4km, ISnobal], Field(discriminator="type")]
