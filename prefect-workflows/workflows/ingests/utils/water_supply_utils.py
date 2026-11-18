"""Shared helpers for water supply volume ingests.

Window variables follow the FVED schema conventions: ``volume_{MMNN}_{statistic}``,
with the window's start and end months, e.g. ``volume_0407_sum`` for Apr-Jul.
"""
from datetime import date
import re
from typing import List, Sequence, Union

import pandas as pd


AF_TO_CUBIC_METERS = 1233.48184

WINDOW_VARIABLE_PATTERN = re.compile(r"^volume_(\d{2})(\d{2})_(sum|cumsum)$")


def water_year(timestamp: Union[date, pd.Timestamp]) -> int:
    """Water year (Oct-Sep), named for the year it ends in."""
    return timestamp.year + 1 if timestamp.month >= 10 else timestamp.year


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
