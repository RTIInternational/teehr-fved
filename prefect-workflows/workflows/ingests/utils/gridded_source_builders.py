from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class GriddedSource(ABC):
    source_bucket: str

    @abstractmethod
    def build_file_list(self, start_dt: datetime, end_dt: datetime) -> list[str]: ...


class UASwan4km(GriddedSource):
    source_bucket = "https://climate.arizona.edu"

    def __init__(self, status: list[str] = None):
        # status controls which data variant to fetch: "stable", "provisional", or "early".
        self.status = status or ["stable", "provisional", "early"]

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
