"""Opt-in regression: run the package end to end for the 2026 dates and compare with the QC-validated live-weights run.

    WSF_RUN_REGRESSION=1 WSF_ROOT=... pytest tests/test_regression.py

Needs network, fetched assets, and tests/reference/live_2026_A.csv (predictions from the same live
weights produced by models/oshbocker_catboost/forecast/run_live_weights.py). Expected: within 2% (live ACIS/SNOTEL data are re-fetched, so a site can move by ~0.1%).
"""

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from oshbocker_infer import cli
from oshbocker_infer.paths import Paths

pytestmark = pytest.mark.skipif(not os.environ.get("WSF_RUN_REGRESSION"), reason="set WSF_RUN_REGRESSION=1 (network + assets)")
REFERENCE = Path(__file__).parent / "reference" / "live_2026_A.csv"


@pytest.mark.parametrize("issue", ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"])
def test_matches_qc_live_run(issue):
    assert cli.main(["run", "--issue-date", issue]) == 0
    got = pd.read_csv(Paths.from_root().output / issue / "forecast.csv").set_index("site_id")
    ref = pd.read_csv(REFERENCE)
    ref = ref[ref.issue_date == issue].set_index("site_id")
    assert len(got) == 26
    for q in ("volume_10", "volume_50", "volume_90"):
        rel = ((got[q] - ref[q].reindex(got.index)) / ref[q].reindex(got.index)).abs()
        assert rel.max() < 0.02, rel.sort_values().tail(3)
