"""Standard folder layout. Everything lives under one root (env WSF_ROOT or --root).

<root>/rasyidstat_3rd/
    assets/         trained weights: models/<variant>/ x 9 (not in git; verified against assets.sha256)
    build/src/      pristine core + static/ metadata + links to assets/ and downloads/ (rebuilt by `build`);
                    this is the working directory of the model (the core reads data/external/... relative to it)
    data/           test_monthly_naturalized_flow.csv (monthly flow, variant A), metadata.csv
    downloads/      raw inputs of the forecast water year: snotel/, cdec/, usgs_streamflow/, usbr/, pdsi/, uaswann/, era5/, seas51/
    preprocessed/   feature caches built from downloads/ (uaswe_*, pdsi, era5, seas51)
    output/<issue_date>/forecast.csv
    logs/
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MODEL_NAME = "rasyidstat_3rd"
MODEL_VERSION = "rasyidstat_3rd_overall_ens9_to2023"
PKG_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paths:
    base: Path

    @classmethod
    def from_root(cls, root: str | Path | None = None) -> "Paths":
        root = Path(root or os.environ.get("WSF_ROOT") or "~/wsf").expanduser().resolve()
        return cls(root / MODEL_NAME)

    assets = property(lambda s: s.base / "assets")
    build = property(lambda s: s.base / "build")
    src = property(lambda s: s.base / "build" / "src")
    data = property(lambda s: s.base / "data")
    downloads = property(lambda s: s.base / "downloads")
    preprocessed = property(lambda s: s.base / "preprocessed")
    output = property(lambda s: s.base / "output")
    logs = property(lambda s: s.base / "logs")

    def ensure(self) -> "Paths":
        for p in (self.assets, self.data, self.downloads, self.preprocessed, self.output, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self
