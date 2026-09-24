"""Gridded data sources for the ingest_gridded_data Prefect flow, selected by their ``type``."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal

from pydantic import BaseModel


class GriddedSource(BaseModel, ABC):
    """A gridded source: its files, its IceChunk repository, and its dataset defaults."""

    source_bucket: ClassVar[str]
    # Source-specific obstore kwargs; deployment obstore_kwargs override them
    store_kwargs: ClassVar[dict] = {}

    @abstractmethod
    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]: ...

    @abstractmethod
    def repository_name(self) -> str:
        """IceChunk repository (configuration) name."""

    @abstractmethod
    def ingest_variables(self) -> list[str]:
        """Source variables to materialize."""

    @abstractmethod
    def dataset_defaults(self) -> dict[str, Any]:
        """Defaults for the ingest input fields; values the caller sets win."""


class UASwan4km(GriddedSource):
    type: Literal["ua-swann-4km"] = "ua-swann-4km"
    # status controls which data variant to fetch: "stable", "provisional", or "early".
    status: list[str] = ["stable", "provisional", "early"]
    variables: list[str] = ["SWE", "DEPTH"]

    source_bucket: ClassVar[str] = "https://climate.arizona.edu"

    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]:
        """Build UA SWANN 4km daily SWE/depth file URLs for the given date range and status(es)."""
        file_list = []
        current = start_dt.date()
        end = end_dt.date()
        while current <= end:
            # Water year starts October 1; directories are organized by water year
            wy = current.year + 1 if current.month >= 10 else current.year
            for s in self.status:
                file_list.append(
                    f"https://climate.arizona.edu/data/UA_SWE/DailyData_4km/"
                    f"WY{wy}/UA_SWE_Depth_4km_v1_{current:%Y%m%d}_{s}.nc"
                )
            current += timedelta(days=1)
        return file_list

    def repository_name(self) -> str:
        return "ua-swann-4km"

    def ingest_variables(self) -> list[str]:
        return list(self.variables)

    def dataset_defaults(self) -> dict[str, Any]:
        return {
            "x_dim": "lon",
            "y_dim": "lat",
            "source_crs": "EPSG:4269",
            "parser_type": "hdf",
            "source_data_storage": "http",
            "obstore_kwargs": {},
            "xconcat_kwargs": {"coords": "minimal", "compat": "override", "combine_attrs": "override"},
        }


# One source type here; with more, use Annotated[Union[...], Field(discriminator="type")]
GriddedSourceType = UASwan4km
