"""Assemble <root>/build/src = pristine core + patches + asset links, and verify checksums.

* core/ must match core.sha256 (it is a byte-identical copy of the competition code: src/ and configs/).
* static/ (public competition files + the model's own metadata) is copied to build/src/data/{meta,raw}.
* patches/*.patch are applied in order with `patch -p1` (every deviation is a reviewable file; see CHANGES.md).
* assets/ must match assets.sha256 (weights are not in git).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .paths import PKG_DIR, Paths

CORE = PKG_DIR / "core"
PATCHES = PKG_DIR / "patches"
STATIC = PKG_DIR / "static"
CORE_MANIFEST = PKG_DIR / "core.sha256"
ASSET_MANIFEST = PKG_DIR / "assets.sha256"
# assets/<rel> is linked to build/src/<rel> for these top-level entries
ASSET_LINKS = ["models"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(directory: Path, out: Path) -> int:
    files = sorted(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    out.write_text("".join(f"{sha256(p)}  {p.relative_to(directory).as_posix()}\n" for p in files))
    return len(files)


def verify_manifest(directory: Path, manifest: Path) -> list[str]:
    """Return problems: missing, changed (and unexpected extra) files."""
    problems = []
    expected = {}
    for line in manifest.read_text().splitlines():
        digest, rel = line.split("  ", 1)
        expected[rel] = digest
    for rel, digest in expected.items():
        f = directory / rel
        if not f.is_file():
            problems.append(f"missing: {rel}")
        elif sha256(f) != digest:
            problems.append(f"changed: {rel}")
    present = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    problems += [f"unexpected: {rel}" for rel in sorted(present - set(expected))]
    return problems


def check_core() -> list[str]:
    return verify_manifest(CORE, CORE_MANIFEST)


def check_assets(paths: Paths) -> list[str]:
    if not paths.assets.is_dir():
        return [f"assets dir not found: {paths.assets}"]
    return verify_manifest(paths.assets, ASSET_MANIFEST)


def build(paths: Paths) -> Path:
    problems = check_core()
    if problems:
        raise RuntimeError("core/ differs from core.sha256:\n  " + "\n  ".join(problems))
    problems = check_assets(paths)
    if problems:
        raise RuntimeError("assets differ from assets.sha256:\n  " + "\n  ".join(problems[:20]))

    if paths.src.exists():
        shutil.rmtree(paths.src)
    shutil.copytree(CORE, paths.src, ignore=shutil.ignore_patterns("__pycache__"))
    applied = []
    for patch in sorted(PATCHES.glob("*.patch")):
        subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-d", str(paths.src), "-i", str(patch)], check=True, capture_output=True)
        applied.append(patch.name)
    for name in ("meta", "raw"):
        shutil.copytree(STATIC / name, paths.src / "data" / name)
    external = paths.src / "data" / "external"
    paths.downloads.mkdir(parents=True, exist_ok=True)
    external.symlink_to(paths.downloads)
    for name in ASSET_LINKS:
        link = paths.src / name
        if link.is_symlink() or link.exists():
            link.unlink() if link.is_symlink() else shutil.rmtree(link)
        link.symlink_to(paths.assets / name)
    (paths.build / "BUILD_INFO.json").write_text(json.dumps({"patches": applied, "core_manifest": sha256(CORE_MANIFEST)}, indent=2))
    return paths.src
