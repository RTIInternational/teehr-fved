from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable


@dataclass
class GriddedSourceConfig:
    """Pairs a source bucket base URL with its file list builder; both must be consistent."""
    source_bucket: str
    build_file_list: Callable[[datetime, datetime], list[str]]


def build_ua_swann_4km_file_list(
    start_dt: datetime,
    end_dt: datetime,
    status: list[str] = ["stable"],
) -> list[str]:
    """Build UA SWANN 4km daily SWE/depth file URLs for the given date range and status(es)."""
    file_list = []
    current = start_dt.date()
    end = end_dt.date()
    while current <= end:
        # Water year starts October 1; directories are organized by water year
        wy = current.year + 1 if current.month >= 10 else current.year
        for s in status:
            file_list.append(
                f"https://climate.arizona.edu/data/UA_SWE/DailyData_4km/"
                f"WY{wy}/UA_SWE_Depth_4km_v1_{current:%Y%m%d}_{s}.nc"
            )
        current += timedelta(days=1)
    return file_list
