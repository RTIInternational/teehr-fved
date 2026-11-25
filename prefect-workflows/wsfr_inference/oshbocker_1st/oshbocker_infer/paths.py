"""Standard folder layout. Everything lives under one root (env WSF_ROOT or --root).

<root>/oshbocker_1st/
    assets/         trained weights (not in git; verified against assets.sha256)
    build/src/      pristine core + patches + assets (rebuilt by `build`)
    data/           competition-runtime layout inputs (metadata.csv, snotel/, usgs_streamflow/, ...)
    downloads/      raw download roots written by the download functions
    preprocessed/   scratch passed to solution.preprocess/predict
    output/<issue_date>/forecast.csv
    logs/
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MODEL_NAME = "oshbocker_1st"
MODEL_VERSION = "oshbocker_1st_live_fs2024"
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
