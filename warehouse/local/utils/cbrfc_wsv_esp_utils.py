from pathlib import Path
import pandas as pd
import numpy as np
import requests

def _build_espmvol_urls(lid: str, years: list[int] = None) -> list[str]:
    """
    Build CBRFC archive URLs for a given location ID and list of 2-digit years.

    Parameters
    ----------
    lid : str
        Location ID (e.g. 'DLAC2')
    years : list[int]
        Two-digit year integers (e.g. [14, 15]). Defaults to [14, 15].

    Returns
    -------
    list[str]
        One URL per month/year combination, in chronological order.
    """
    if years is None:
        years = [14, 15]

    months = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]

    base = "http://www.cbrfc.noaa.gov/outgoing/32month/archive/raw"

    urls = []
    for yy in years:
        yy_str = f"{yy:02d}"
        for mmm in months:
            slug = f"{mmm}{yy_str}"
            urls.append(f"{base}/{slug}/RAW.{lid}.{slug}.txt")

    return urls

def _read_espmvol_forecast(source):
    """
    Parse a CBRFC espmvol forecast file into a long-form DataFrame.

    Parameters
    ----------
    source : str or Path
        A URL string (http/https) or a local file path.

    Returns
    -------
    pd.DataFrame with columns ['reference_time', 'value_time', 'value', 'member']
    """

    source_str = str(source)

    if source_str.startswith("http://") or source_str.startswith("https://"):
        try:
            resp = requests.get(source_str, timeout=30)
            resp.raise_for_status()
            lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"HTTP error fetching {source_str}: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Connection error fetching {source_str}: {e}") from e
        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"Request timed out fetching {source_str}: {e}") from e
    else:
        try:
            with Path(source).open("r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except FileNotFoundError as e:
            raise RuntimeError(f"File not found: {source}") from e

    if len(lines) < 4:
        raise ValueError(f"Expected at least 4 non-empty lines in source: {source_str}")

    reference_time = pd.to_datetime(lines[1]).normalize()

    header_parts = lines[2].split()
    if len(header_parts) < 3 or header_parts[0] != "traces" or header_parts[1] != "->":
        raise ValueError(f"Could not parse member headers from the third line of: {source_str}")

    members = header_parts[2:]

    records = []
    for row in lines[3:]:
        parts = row.split()
        if len(parts) != len(members) + 1:
            raise ValueError(
                f"Row has {len(parts) - 1} values but expected {len(members)}: {row}"
            )
        value_time = pd.to_datetime(parts[0], format="%m/%Y")
        values = pd.to_numeric(parts[1:], errors="raise")
        for member, value in zip(members, values):
            records.append({
                "reference_time": reference_time,
                "value_time": value_time,
                "value": float(value),
                "member": member,
            })

    df = pd.DataFrame(records, columns=["reference_time", "value_time", "value", "member"])

    # convert 'value' from kaf to cubic meters
    df["value"] = np.round((df["value"]*1000) * 1233.48184, 3)
    df['unit_name'] = 'm^3'

    return df

def query_espmvol_forecast(
        lid: str, 
        years: list[int] = None,
        constant_field_values: dict = None
        ) -> pd.DataFrame:
    """
    Fetch and combine all archived espmvol forecast files for a given LID.

    Parameters
    ----------
    lid : str
        Location ID (e.g. 'DLAC2')
    years : list[int], optional
        Two-digit year integers (e.g. [14, 15]). Defaults to [14, 15].

    Returns
    -------
    pd.DataFrame with columns ['reference_time', 'value_time', 'value', 'member'],
    combining all successfully fetched forecast files in chronological order.
    """
    urls = _build_espmvol_urls(lid, years)
    frames = []
    failed = []

    for url in urls:
        try:
            df = _read_espmvol_forecast(url)
            frames.append(df)
        except RuntimeError as e:
            print(f"[WARN] Could not fetch {url}: {e}")
            failed.append(url)
        except (ValueError, Exception) as e:
            print(f"[WARN] Could not parse {url}: {e}")
            failed.append(url)

    if not frames:
        raise RuntimeError(
            f"No forecast data could be retrieved for LID '{lid}'. "
            f"All {len(failed)} endpoints failed."
        )

    if failed:
        print(f"[INFO] {len(frames)} files ingested successfully, {len(failed)} failed for LID '{lid}'.")

    combined = pd.concat(frames, ignore_index=True)
    combined.sort_values(["reference_time", "member", "value_time"], inplace=True, ignore_index=True)

    # add the constant field values
    for key, value in constant_field_values.items():
        combined[key] = value

    return combined