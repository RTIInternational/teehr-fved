"""Regression tests for run_postprocessing against the March 2025 CRMMS model output."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from riverware.postprocessing.load_results import run_postprocessing, save_parquet

EXPECTED_COLUMNS = {
    "reference_time", "value_time", "configuration_name",
    "unit_name", "variable_name", "value", "location_id", "member",
}
EXPECTED_MEMBERS = {str(i) for i in range(2, 34)}
EXPECTED_REFERENCE_TIME = datetime(2025, 4, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def df(model_dir):
    return run_postprocessing(
        model_dir=model_dir,
        configuration_name="crmms_esp_march2025",
    )


def test_columns(df):
    assert set(df.columns) == EXPECTED_COLUMNS


def test_row_count_stable(df):
    # Baseline row count — update this if model outputs change
    assert len(df) > 100_000


def test_reference_time(df):
    assert df["reference_time"].iloc[0].to_pydatetime() == EXPECTED_REFERENCE_TIME


def test_all_members_present(df):
    assert set(df["member"].unique()) == EXPECTED_MEMBERS


def test_timestamp_dtypes(df):
    assert str(df["reference_time"].dtype) == "datetime64[us, UTC]"
    assert str(df["value_time"].dtype) == "datetime64[us, UTC]"


def test_parquet_roundtrip(df, tmp_path):
    out = tmp_path / "crmms_esp.parquet"
    save_parquet(df, out)
    result = pd.read_parquet(out)
    assert len(result) == len(df)
    assert set(result.columns) == EXPECTED_COLUMNS
