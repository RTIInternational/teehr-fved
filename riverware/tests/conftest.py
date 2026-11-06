from datetime import timezone
from pathlib import Path

import pytest

MODEL_DIR = Path(r"C:\FVED\Models\CRMMS-ESP\CRMMS-March2025")


@pytest.fixture(scope="session")
def model_dir():
    if not MODEL_DIR.exists():
        pytest.skip(f"Model directory not found: {MODEL_DIR}")
    return MODEL_DIR


@pytest.fixture(scope="session")
def rdf_dir(model_dir):
    return model_dir / "rdfOutput"


@pytest.fixture(scope="session")
def log_path(model_dir):
    return model_dir / "run.log"


@pytest.fixture(scope="session")
def annual_rdf(rdf_dir):
    return rdf_dir / "annualEIS.rdf"
