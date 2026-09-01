"""
RandomWoods annual input data pre-processing -- Lees Ferry naturalized flow
+ AMO/PDO ocean indices.

Downloads the three annually-refreshed inputs the RandomWoods forecast
needs and saves them as local files for RandomWoods_Forecast.R to read.
Combined into one script (rather than separate `ingests/` entries) because
this data is only ever used locally for a single RandomWoods model run --
it is not persisted to the TEEHR data warehouse.

Sources:
    Lees Ferry naturalized flow (USBR provisional 24-Month Study estimate):
        https://www.usbr.gov/lc/region/g4000/NaturalFlow/provisional.html
    AMO index (NOAA ERSST v5):
        https://www1.ncdc.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.amo.dat
    PDO index (NOAA ERSST v5):
        https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat

Why the *provisional* USBR page and not the final published record
(https://www.usbr.gov/lc/region/g4000/NaturalFlow/current.html)? USBR
publishes a provisional early estimate after each 24-Month Study (January,
April, August). The August estimate is the freshest one available before
the October 1 RandomWoods forecast issuance -- the final/"current" record
for a given water year typically lags well behind that.

Why download AMO/PDO annually instead of RandomWoods_Forecast.R fetching
them live from NOAA on every run (as the original notebook did)?
RandomWoods only runs once a year, right before October 1, by which point
the JAS (Jul-Aug-Sep) mean these indices feed into is already final --
there's nothing to gain from a live fetch at run time, only an extra
network dependency inside the forecast container and a loss of
run-to-run reproducibility (NOAA does occasionally revise historical
months in place). So all three inputs are downloaded together, once a
year, right before the forecast run.

Usage:
    python -m workflows.crmms_forecasts.randomwoods.download_inputs \
        --output-dir /data/randomwoods/annual
"""
from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests

logging.basicConfig(level="INFO")
logger = logging.getLogger("crmms_forecasts.randomwoods.download_inputs")

# ---- Lees Ferry naturalized flow ----

LF_PROVISIONAL_PAGE_URL = "https://www.usbr.gov/lc/region/g4000/NaturalFlow/provisional.html"

# Standardized filename RandomWoods_Forecast.R reads via LF_NATFLOW_FILE.
LF_STANDARDIZED_FILENAME = "LFnatFlow_latest.xlsx"

# Matches USBR's filename convention, e.g. LFnatFlow1906-2024.2024.9.12.xlsx
LF_FILENAME_PATTERN = re.compile(
    r"LFnatFlow(?P<start_year>\d{4})-(?P<end_year>\d{4})\."
    r"(?P<pub_year>\d{4})\.(?P<pub_month>\d{1,2})\.(?P<pub_day>\d{1,2})\.xlsx",
    re.IGNORECASE,
)


@dataclass
class NaturalFlowLink:
    url: str
    end_year: int
    published: date

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def _find_natural_flow_links(page_html: str, page_url: str) -> list[NaturalFlowLink]:
    """Parse all Lees Ferry natural flow .xlsx links out of a USBR page's HTML."""
    links = []
    for match in re.finditer(r'href="([^"]+\.xlsx)"', page_html, re.IGNORECASE):
        href = match.group(1)
        name_match = LF_FILENAME_PATTERN.search(href)
        if not name_match:
            continue  # skip unrelated .xlsx links, if any
        links.append(
            NaturalFlowLink(
                url=urljoin(page_url, href),
                end_year=int(name_match.group("end_year")),
                published=date(
                    int(name_match.group("pub_year")),
                    int(name_match.group("pub_month")),
                    int(name_match.group("pub_day")),
                ),
            )
        )
    return links


def download_lees_ferry_natural_flow(
    output_dir: Path,
    page_url: str = LF_PROVISIONAL_PAGE_URL,
) -> Path:
    """Download the latest provisional Lees Ferry natural flow workbook.

    Saves it under both its original USBR filename (for audit/provenance)
    and as `LFnatFlow_latest.xlsx`. Picks the link with the most recent
    publish date embedded in its filename (not just page position, since
    the page typically lists several prior 24-Month-Study-based estimates
    and that order isn't guaranteed).

    Returns the path to the standardized-name copy.
    """
    logger.info("Fetching %s", page_url)
    resp = requests.get(page_url, timeout=30)
    resp.raise_for_status()

    links = _find_natural_flow_links(resp.text, page_url)
    if not links:
        raise RuntimeError(f"No Lees Ferry natural flow .xlsx links found on {page_url}")

    latest = max(links, key=lambda l: l.published)
    logger.info(
        "Latest available: %s (published %s, covers through WY%s)",
        latest.filename, latest.published, latest.end_year,
    )

    logger.info("Downloading %s", latest.url)
    resp = requests.get(latest.url, timeout=60)
    resp.raise_for_status()

    original_path = output_dir / latest.filename
    original_path.write_bytes(resp.content)
    logger.info("Saved %s (%d bytes)", original_path, len(resp.content))

    standardized_path = output_dir / LF_STANDARDIZED_FILENAME
    standardized_path.write_bytes(resp.content)
    logger.info("Saved standardized copy %s", standardized_path)

    return standardized_path


# ---- AMO / PDO ocean indices ----

AMO_URL = "https://www1.ncdc.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.amo.dat"
PDO_URL = "https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat"

# Standardized filenames RandomWoods_Forecast.R reads via AMO_FILE / PDO_FILE.
AMO_STANDARDIZED_FILENAME = "AMO_latest.dat"
PDO_STANDARDIZED_FILENAME = "PDO_latest.dat"


def _download_ocean_index(name: str, url: str, output_dir: Path, standardized_filename: str) -> Path:
    """Download one NOAA index file, saving both a dated audit copy (since
    the source URL has no version/date in its own name) and the
    standardized-name copy RandomWoods_Forecast.R reads by default."""
    logger.info("Downloading %s from %s", name, url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    today = date.today().isoformat()
    dated_path = output_dir / f"{name.lower()}_asof_{today}.dat"
    dated_path.write_bytes(resp.content)
    logger.info("Saved dated audit copy %s (%d bytes)", dated_path, len(resp.content))

    standardized_path = output_dir / standardized_filename
    standardized_path.write_bytes(resp.content)
    logger.info("Saved standardized copy %s", standardized_path)

    return standardized_path


def download_ocean_indices(
    output_dir: Path,
    amo_url: str = AMO_URL,
    pdo_url: str = PDO_URL,
) -> tuple[Path, Path]:
    """Download the current AMO and PDO index files.

    Returns (amo_standardized_path, pdo_standardized_path).
    """
    amo_path = _download_ocean_index("AMO", amo_url, output_dir, AMO_STANDARDIZED_FILENAME)
    pdo_path = _download_ocean_index("PDO", pdo_url, output_dir, PDO_STANDARDIZED_FILENAME)
    return amo_path, pdo_path


# ---- Combined entry point ----

def download_annual_inputs(
    output_dir: str | Path,
    lf_page_url: str = LF_PROVISIONAL_PAGE_URL,
    amo_url: str = AMO_URL,
    pdo_url: str = PDO_URL,
) -> dict[str, Path]:
    """Download all three annual RandomWoods inputs into output_dir.

    Returns a dict with keys "lf_natflow", "amo", "pdo" mapping to the
    standardized-name file paths RandomWoods_Forecast.R reads by default
    (LFnatFlow_latest.xlsx, AMO_latest.dat, PDO_latest.dat).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lf_path = download_lees_ferry_natural_flow(output_dir, lf_page_url)
    amo_path, pdo_path = download_ocean_indices(output_dir, amo_url, pdo_url)

    return {"lf_natflow": lf_path, "amo": amo_path, "pdo": pdo_path}


if __name__ == "__main__":
    default_output_dir = Path(__file__).resolve().parent / "annual_inputs"

    parser = argparse.ArgumentParser(
        description="Download RandomWoods' annual inputs: Lees Ferry naturalized flow + AMO/PDO ocean indices."
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir),
        help=f"Directory to save the downloaded files into (default: {default_output_dir})",
    )
    parser.add_argument("--lf-page-url", default=LF_PROVISIONAL_PAGE_URL, help="USBR provisional data page URL")
    parser.add_argument("--amo-url", default=AMO_URL, help="AMO index source URL")
    parser.add_argument("--pdo-url", default=PDO_URL, help="PDO index source URL")
    args = parser.parse_args()

    paths = download_annual_inputs(args.output_dir, args.lf_page_url, args.amo_url, args.pdo_url)
    for name, path in paths.items():
        print(f"Downloaded {name} to: {path}")
