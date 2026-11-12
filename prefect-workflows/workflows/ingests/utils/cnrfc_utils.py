"""Shared helpers for CNRFC (California Nevada River Forecast Center) ingests."""
import re
from typing import List, Optional, Tuple

import pandas as pd
import requests
from prefect import task, get_run_logger

from utils.water_supply_utils import AF_TO_CUBIC_METERS


CNRFC_TABULAR_URL = "https://www.cnrfc.noaa.gov/ensembleProductTabular.php"
LOCATION_ID_PREFIX = "cnrfc"
HTTP_TIMEOUT_SECONDS = (30, 300)  # (connect, read); the site can be slow
CNRFC_TIME_ZONE = "America/Los_Angeles"
KAF_TO_CUBIC_METERS = 1000 * AF_TO_CUBIC_METERS

# Ensemble trend plot products (tabular view)
SEASONAL_PRODUCT_ID = 7  # Seasonal window, usually Apr-Jul (Apr-Sep at some points)
WATER_YEAR_PRODUCT_ID = 9  # Oct-Sep

MONTH_NUMBERS = {
    name: number for number, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}
OBSERVED_TO_DATE = "observed_to_date"


@task(retries=2, retry_delay_seconds=30)
def fetch_tabular_page(station_id: str, product_id: int, water_year: int) -> str:
    """Fetch the tabular trend plot page for one station, product and water year."""
    logger = get_run_logger()
    params = {"id": station_id, "prodID": product_id, "year": water_year}
    logger.info(f"Fetching CNRFC tabular product: {params}")
    response = requests.get(CNRFC_TABULAR_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _window_variable_name(label: str) -> str:
    """Window volume variable from a forecast column label, e.g. ``volume_0407_sum``."""
    match = re.search(r"\b([A-Z][a-z]{2})-([A-Z][a-z]{2})\b", label)
    if match:
        start_month, end_month = (MONTH_NUMBERS[name] for name in match.groups())
    elif "WY" in label:
        start_month, end_month = 10, 9
    else:
        raise ValueError(f"No forecast window in CNRFC column label: {label}")
    return f"volume_{start_month:02d}{end_month:02d}_sum"


def _member(label: str) -> str:
    """Member from a forecast column label: ``min``, ``max`` or ``p{exceedance}``."""
    if label.startswith("Min"):
        return "min"
    if label.startswith("Max"):
        return "max"
    return f"p{re.match(r'(\d+)%', label).group(1)}"


def _column_labels(header_lines: List[str], anchors: List[int]) -> List[str]:
    """Join the header words above each column, assigning words by position."""
    labels = [[] for _ in anchors]
    for line in header_lines:
        for word in re.finditer(r"\S+", line[1:]):
            start = word.start() + 1
            columns = [i for i, anchor in enumerate(anchors) if anchor <= start + 2]
            if columns:
                labels[columns[-1]].append(word.group())
    return [" ".join(words) for words in labels]


def parse_tabular_page(html: str) -> Tuple[Optional[str], pd.DataFrame]:
    """Parse a tabular trend plot page.

    Returns the window variable name (e.g. ``volume_0407_sum``) and a DataFrame
    with ``date`` (issue date), one column per forecast member and
    ``observed_to_date``, in kaf. Returns ``(None, empty DataFrame)`` when the
    product isn't available for the station and year.

    The table is fixed width with blank cells, so values are assigned to
    columns by position, using the units row as column anchors. Rows with
    ``Missing`` forecasts are wider, so only their trailing values are read.
    """
    match = re.search(r"<pre>(.*?)</pre>", html, re.S)
    if match is None:
        return None, pd.DataFrame()
    lines = match.group(1).splitlines()

    units_index = next(i for i, line in enumerate(lines) if "(kaf)" in line)
    anchors = [unit.start() for unit in re.finditer(r"\(kaf\)", lines[units_index])]
    header_lines = []
    for line in reversed(lines[:units_index]):
        if line.strip() == "#":
            break
        header_lines.insert(0, line)
    labels = _column_labels(header_lines, anchors)

    forecast_columns = {i: _member(label) for i, label in enumerate(labels) if "Exceed" in label}
    observed_columns = [i for i, label in enumerate(labels) if "To Date" in label and "Obs" in label]
    if not forecast_columns or len(observed_columns) != 1:
        raise ValueError(f"Unexpected CNRFC table columns: {labels}")
    variable_name = _window_variable_name(labels[min(forecast_columns)])

    rows = []
    for line in lines:
        if not re.match(r"\s*\d\d/\d\d/\d{4}", line):
            continue
        values = [None] * len(anchors)
        if "Missing" in line:
            # No forecast that day; trailing values fill the last columns
            trailing = line.split("</i>")[-1].split()
            for offset, value in enumerate(reversed(trailing), start=1):
                values[-offset] = float(value)
        else:
            for token in re.finditer(r"\S+", line):
                if token.start() < anchors[0] - 4:
                    continue  # Date
                column = max(i for i, anchor in enumerate(anchors) if anchor <= token.end() - 1)
                values[column] = float(token.group())
        rows.append({
            "date": pd.to_datetime(line.split()[0], format="%m/%d/%Y"),
            **{member: values[i] for i, member in forecast_columns.items()},
            OBSERVED_TO_DATE: values[observed_columns[0]],
        })
    return variable_name, pd.DataFrame(rows).astype(
        {member: float for member in [*forecast_columns.values(), OBSERVED_TO_DATE]}
    )
