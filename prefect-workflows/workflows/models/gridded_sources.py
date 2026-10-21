"""Gridded data sources for the ingest_gridded_data Prefect flow, selected by their ``type``."""
import os
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Annotated, ClassVar, Literal, Union

import obstore
import pandas as pd
import requests
import xarray as xr
from obstore.store import from_url
from prefect.blocks.system import Secret
from pydantic import AfterValidator, BaseModel, Field
from teehr.fetching.utils import REMOTE_RETRY_CONFIG

from workflows.utils.data_status import STATUS_COORD, STATUS_MEANINGS, with_status

# Columns of a source listing, indexed by each file's timestamp
LISTING_COLUMNS = ["url", STATUS_COORD, "last_modified"]


class GriddedSource(BaseModel, ABC):
    """A gridded source: its files, its time grid, and its IceChunk repository."""

    source_bucket: ClassVar[str]
    # Source-specific obstore kwargs; deployment obstore_kwargs override them
    store_kwargs: ClassVar[dict] = {}
    # Options for the IceChunk virtual chunk container's object store, e.g. region
    virtual_store_kwargs: ClassVar[dict] = {}
    time_step: ClassVar[pd.Timedelta]

    @abstractmethod
    def list_files(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Files published for the range, one per step: ``LISTING_COLUMNS`` indexed by time."""

    @abstractmethod
    def time_origin(self) -> pd.Timestamp:
        """First step of the source's record; the repo's time grid starts here."""

    @abstractmethod
    def repository_name(self) -> str:
        """IceChunk repository (configuration) name; teehr-valid (letters, digits, underscores)."""

    @abstractmethod
    def ingest_variables(self) -> list[str]:
        """Source variables to materialize."""

    def grid_name(self) -> str:
        """Grid (CRS, pixel size, extent) the source's data is on; sources sharing a grid share a name."""
        return self.repository_name()

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


def _listing(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["time", *LISTING_COLUMNS])
    return df.set_index(pd.DatetimeIndex(df.pop("time"), name="time")).sort_index()


def _known_status(v: str) -> str:
    if v not in STATUS_MEANINGS:
        raise ValueError(f"status must be one of {STATUS_MEANINGS}, got '{v}'")
    return v


# Data status recorded for every step of a source that publishes one status
Status = Annotated[str, AfterValidator(_known_status), Field(description=f"Data status recorded for every step: one of {STATUS_MEANINGS}")]


def _secret_credentials(name: str) -> dict:
    """S3 keys from the ``<name>-aws-*`` Prefect Secret blocks; env vars (e.g. set in a notebook) take precedence."""
    blocks = {"access_key_id": f"{name}-aws-access-key-id", "secret_access_key": f"{name}-aws-secret-access-key"}
    return {
        key: os.environ.get(block.upper().replace("-", "_")) or Secret.load(block).get()
        for key, block in blocks.items()
    }


def _keyed_store(source: GriddedSource):
    """An obstore store for the source's bucket, signed with its credentials."""
    # A provider rather than keys: with keys, obstore adds any ambient AWS_SESSION_TOKEN to the request
    creds = {**source.credentials(), "token": None, "expires_at": None}
    return from_url(f"{source.source_bucket}/", **source.store_kwargs, credential_provider=lambda: creds)


class UASwan4km(GriddedSource):
    type: Literal["ua-swann-4km"] = "ua-swann-4km"
    # Variants that may be used; each day takes the most final one published
    status: list[str] = ["stable", "provisional", "early"]
    variables: list[str] = ["SWE", "DEPTH"]

    source_bucket: ClassVar[str] = "https://climate.arizona.edu"
    base_url: ClassVar[str] = "https://climate.arizona.edu/data/UA_SWE/DailyData_4km"
    time_step: ClassVar[pd.Timedelta] = pd.Timedelta("1D")
    # A listing row: file name, then its last-modified time (the server's local time; only compared with itself)
    row_pattern: ClassVar[re.Pattern] = re.compile(
        r'href="(UA_SWE_Depth_4km_v1_(\d{8})_(early|provisional|stable)\.nc)".*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'
    )

    def list_files(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """One file per day in the range: the most final allowed variant in each water year's directory."""
        start, end = start_dt.date(), end_dt.date()
        best: dict[date, dict] = {}
        for wy in range(_water_year(start), _water_year(end) + 1):
            resp = requests.get(f"{self.base_url}/WY{wy}/", timeout=60)
            if resp.status_code == 404:  # water year not published yet
                continue
            resp.raise_for_status()
            for name, stamp, status, modified in self.row_pattern.findall(resp.text):
                day = datetime.strptime(stamp, "%Y%m%d").date()
                if status not in self.status or not start <= day <= end:
                    continue
                if day not in best or STATUS_MEANINGS.index(status) > STATUS_MEANINGS.index(best[day][STATUS_COORD]):
                    best[day] = {
                        "time": pd.Timestamp(day),
                        "url": f"{self.base_url}/WY{wy}/{name}",
                        STATUS_COORD: status,
                        "last_modified": pd.Timestamp(modified),
                    }
        return _listing(list(best.values()))

    def time_origin(self) -> pd.Timestamp:
        # The archive starts with WY1982
        return pd.Timestamp("1981-10-01T00:00")

    def repository_name(self) -> str:
        return "ua_swann_4km"

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
    status: Status = "stable"

    source_bucket: ClassVar[str] = "s3://m3w-transfer"
    store_kwargs: ClassVar[dict] = {"region": "us-west-2", "retry_config": REMOTE_RETRY_CONFIG}
    virtual_store_kwargs: ClassVar[dict] = {"region": "us-west-2"}
    time_step: ClassVar[pd.Timedelta] = pd.Timedelta("1D")
    # Units per variable; only some files carry a units tag
    units: ClassVar[dict] = {"specific_mass": "kg m-2"}

    def list_files(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Files laid out as <domain>/wy<YYYY>/run<YYYYMMDD>/<variable>_<time>.tif, listed per water year."""
        start, end = start_dt.date(), end_dt.date()
        pattern = re.compile(rf"/run\d{{8}}/{re.escape(self.variable)}_(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}:\d{{2}})\.tif$")
        store, rows = _keyed_store(self), []
        for wy in range(_water_year(start), _water_year(end) + 1):
            for batch in obstore.list(store, prefix=f"{self.prefix}/{self.domain}/wy{wy}/"):
                for obj in batch:
                    match = pattern.search(obj["path"])
                    if match and start <= pd.Timestamp(match.group(1)).date() <= end:
                        rows.append({
                            "time": pd.Timestamp(match.group(1)),
                            "url": f"{self.source_bucket}/{obj['path']}",
                            STATUS_COORD: self.status,
                            "last_modified": pd.Timestamp(obj["last_modified"]).tz_convert(None),
                        })
        return _listing(rows)

    def time_origin(self) -> pd.Timestamp:
        """Start of the domain's first water year in the bucket; domains start in different years."""
        listed = obstore.list_with_delimiter(_keyed_store(self), prefix=f"{self.prefix}/{self.domain}/")
        matches = (re.search(r"/wy(\d{4})/?$", p) for p in listed["common_prefixes"])
        years = sorted(int(m.group(1)) for m in matches if m)
        if not years:
            raise ValueError(f"No water years found for iSnobal domain '{self.domain}'.")
        return pd.Timestamp(f"{years[0] - 1}-10-01T23:00")

    def repository_name(self) -> str:
        return f"isnobal_{self.domain}"

    def ingest_variables(self) -> list[str]:
        return [self.variable]

    def credentials(self) -> dict:
        return _secret_credentials("m3works")

    def preprocess(self, ds: xr.Dataset, url: str) -> xr.Dataset:
        # Parsed with IFD 0 (full resolution), the only variable is "0"
        time = pd.Timestamp(url.rsplit("_", 1)[-1].removesuffix(".tif"))
        ds = ds.rename({"0": self.variable}).expand_dims(time=[time])
        if self.variable in self.units:
            ds[self.variable].attrs.setdefault("units", self.units[self.variable])
        return with_status(ds, self.status)


class CUSwe(GriddedSource):
    """CU Boulder SWE fusion, one daily western U.S. GeoTIFF."""

    type: Literal["cu-swe"] = "cu-swe"
    prefix: str = Field(default="NRT", description="Key prefix of the daily files")
    variable: str = Field(default="SWE", description="Name given to the files' only band")
    status: Status = "stable"

    source_bucket: ClassVar[str] = "s3://swe-fusion"
    store_kwargs: ClassVar[dict] = {"region": "us-east-2", "retry_config": REMOTE_RETRY_CONFIG}
    virtual_store_kwargs: ClassVar[dict] = {"region": "us-east-2"}
    time_step: ClassVar[pd.Timedelta] = pd.Timedelta("1D")
    # The files carry no units tag; m is unconfirmed. Ingest converts to mm.
    units: ClassVar[str] = "m"
    file_pattern: ClassVar[re.Pattern] = re.compile(r"/WW_phvrcn_(\d{8})_fscamsk_clp\.tif$")

    def _files(self) -> list[tuple[pd.Timestamp, dict]]:
        """(day, object meta) of every file under the prefix; the keys can't list the bucket root."""
        files = []
        for batch in obstore.list(_keyed_store(self), prefix=f"{self.prefix}/"):
            for obj in batch:
                match = self.file_pattern.search(obj["path"])
                if match:
                    files.append((pd.Timestamp(match.group(1)), obj))
        return files

    def list_files(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        start, end = start_dt.date(), end_dt.date()
        return _listing([
            {
                "time": day,
                "url": f"{self.source_bucket}/{obj['path']}",
                STATUS_COORD: self.status,
                "last_modified": pd.Timestamp(obj["last_modified"]).tz_convert(None),
            }
            for day, obj in self._files() if start <= day.date() <= end
        ])

    def time_origin(self) -> pd.Timestamp:
        """First day published under the prefix."""
        days = [day for day, _ in self._files()]
        if not days:
            raise ValueError(f"No CU-SWE files found under '{self.source_bucket}/{self.prefix}/'.")
        return min(days)

    def repository_name(self) -> str:
        return "cu_swe"

    def ingest_variables(self) -> list[str]:
        return [self.variable]

    def credentials(self) -> dict:
        return _secret_credentials("cu-swe")

    def preprocess(self, ds: xr.Dataset, url: str) -> xr.Dataset:
        # Parsed with IFD 0 (full resolution), the only variable is "0"
        time = pd.Timestamp(self.file_pattern.search(url).group(1))
        ds = ds.rename({"0": self.variable}).expand_dims(time=[time])
        ds[self.variable].attrs.setdefault("units", self.units)
        return with_status(ds, self.status)


GriddedSourceType = Annotated[Union[UASwan4km, ISnobal, CUSwe], Field(discriminator="type")]
