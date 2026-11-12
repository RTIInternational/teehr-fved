"""Shared helpers for water supply volume ingests.

Window variables follow the FVED schema conventions: ``volume_{MMNN}_{statistic}``,
with the window's start and end months, e.g. ``volume_0407_sum`` for Apr-Jul.
"""
from datetime import date, datetime
from pathlib import Path
import re
from typing import Dict, List, Sequence, Union

import pandas as pd
from prefect import get_run_logger
import teehr
from teehr.fetching.utils import write_timeseries_parquet_file

from workflows.utils.common_utils import load_to_warehouse


AF_TO_CUBIC_METERS = 1233.48184

WINDOW_VARIABLE_PATTERN = re.compile(r"^volume_(\d{2})(\d{2})_(sum|cumsum)$")

SECONDARY_COLUMNS = [
    "reference_time", "value_time", "value", "variable_name",
    "configuration_name", "unit_name", "location_id", "member",
]
PRIMARY_COLUMNS = SECONDARY_COLUMNS[:-1]
TIMESERIES_TABLES = ("secondary_timeseries", "primary_timeseries")


def water_year(timestamp: Union[date, pd.Timestamp]) -> int:
    """Water year (Oct-Sep), named for the year it ends in."""
    return timestamp.year + 1 if timestamp.month >= 10 else timestamp.year


def water_year_range(
    start_date: Union[str, date, datetime, None],
    end_date: Union[str, date, datetime, None],
) -> range:
    """Water years to fetch, by default the previous and current ones."""
    last_water_year = water_year(pd.Timestamp(end_date or date.today()))
    if start_date is None:
        return range(last_water_year - 1, last_water_year + 1)
    return range(water_year(pd.Timestamp(start_date)), last_water_year + 1)


def cache_water_year(
    cache_dir: Path,
    water_year: int,
    timeseries: Dict[str, pd.DataFrame],
) -> None:
    """Write one water year of formatted timeseries to parquet, one dir per table."""
    for table_name, df in timeseries.items():
        if df.empty:
            continue
        table_dir = Path(cache_dir, table_name)
        table_dir.mkdir(parents=True, exist_ok=True)
        write_timeseries_parquet_file(
            filepath=Path(table_dir, f"wy{water_year}.parquet"),
            overwrite_output=True,
            data=df,
            timeseries_type=table_name.split("_")[0],
        )


def load_cached_timeseries(ev: teehr.Evaluation, cache_dir: Path) -> None:
    """Upsert each cached table into the warehouse, so revisions replace old values."""
    logger = get_run_logger()
    for table_name in TIMESERIES_TABLES:
        table_dir = Path(cache_dir, table_name)
        if not any(table_dir.glob("*.parquet")):
            logger.info(f"No {table_name} data cached. Skipping load.")
            continue
        load_to_warehouse(
            ev=ev,
            in_path=table_dir,
            table_name=table_name,
            write_mode="upsert",
        )


def window_months(variable_name: str, water_year: int) -> pd.DatetimeIndex:
    """Month starts of a window variable's window in a water year."""
    match = WINDOW_VARIABLE_PATTERN.match(variable_name)
    if match is None:
        raise ValueError(f"Not a window volume variable: {variable_name}")
    start_month, end_month = int(match.group(1)), int(match.group(2))
    start_year = water_year - 1 if start_month >= 10 else water_year
    return pd.date_range(
        pd.Timestamp(start_year, start_month, 1),
        periods=(end_month - start_month) % 12 + 1,
        freq="MS",
    )


def seasonal_volumes(
    monthly_df: pd.DataFrame,
    variable_names: List[str],
    cumsum_variable_names: List[str],
    water_year: int,
    group_by: Sequence[str] = ("location_id", "unit_name"),
) -> pd.DataFrame:
    """Window totals and running totals from monthly volumes.

    ``monthly_df`` has the ``group_by`` columns, ``value_time`` (month start)
    and ``value``. A window total is written only when every month of the
    window is present, at the window start. Running totals are written for
    each completed month, at the start of the next month.
    """
    rows = []
    for keys, group in monthly_df.groupby(list(group_by)):
        by_month = group.set_index("value_time")["value"]
        for variable_name in variable_names:
            months = window_months(variable_name, water_year)
            if months.isin(by_month.index).all():
                rows.append((*keys, months[0], by_month[months].sum(), variable_name))
        for variable_name in cumsum_variable_names:
            running_total = 0.0
            for month in window_months(variable_name, water_year):
                if month not in by_month.index:
                    break
                running_total += by_month[month]
                rows.append((*keys, month + pd.offsets.MonthBegin(1), running_total, variable_name))
    return pd.DataFrame(
        rows, columns=[*group_by, "value_time", "value", "variable_name"]
    ).astype({"value_time": "datetime64[ns]", "value": float})
