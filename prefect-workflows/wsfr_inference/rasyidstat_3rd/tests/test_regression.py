"""Opt-in regression: run the package end to end for the 2026 dates and compare with the QC-validated wrapper run.

    WSF_RUN_REGRESSION=1 WSF_ROOT=... pytest tests/test_regression.py

Needs network, CDS credentials, fetched assets, and tests/reference/forecast_2026_first_of_month.csv (the QC wrapper's
2026 predictions, identical to the package engine on the same inputs). Run it ~a week after the last issue date so that
ERA5-Land and SEAS5.1 cover every date (otherwise variants are left out and the ensemble differs). Live data are re-fetched,
so sites can move slightly: tolerance 2%.
"""

import os
from pathlib import Path

import pandas as pd
import pytest

from rasyidstat_infer import cli
from rasyidstat_infer.paths import Paths

pytestmark = pytest.mark.skipif(not os.environ.get("WSF_RUN_REGRESSION"), reason="set WSF_RUN_REGRESSION=1 (network + assets)")
REFERENCE = Path(__file__).parent / "reference" / "forecast_2026_first_of_month.csv"


@pytest.mark.parametrize("issue", ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"])
def test_matches_qc_wrapper_run(issue):
    assert cli.main(["run", "--issue-date", issue, "--strict"]) == 0
    got = pd.read_csv(Paths.from_root().output / issue / "forecast.csv").set_index("site_id")
    ref = pd.read_csv(REFERENCE)
    ref = ref[ref.issue_date == issue].set_index("site_id")
    assert len(got) == 26
    for q in ("volume_10", "volume_50", "volume_90"):
        rel = ((got[q] - ref[q].reindex(got.index)) / ref[q].reindex(got.index)).abs()
        assert rel.max() < 0.02, rel.sort_values().tail(3)
