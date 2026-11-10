"""CLI: python -m oshbocker_infer <command> [--root DIR]

    build            assemble <root>/oshbocker_1st/build/src from core/ + patches/ + assets/
    check-assets     verify assets/ against assets.sha256 (and core/ against core.sha256)
    fetch-assets     copy assets from a shared directory or s3:// URI, then verify
    check-sources    ping every external endpoint and verify the response shape (--sources to pick probes); exit 1 on failure
    manifest         (maintainers) rewrite core.sha256 / assets.sha256
    download         fetch SNOTEL, USGS and monthly flow for --issue-date
    predict          forecast every site for --issue-date -> output/<issue_date>/forecast.csv
    run              download + build (if needed) + predict
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import build as build_mod
from . import schema
from .paths import Paths


def _issue(s: str) -> date:
    return date.fromisoformat(s)


def cmd_predict(paths: Paths, issue_date: date, sites, out: Path | None, allow_partial: bool) -> int:
    from . import solution

    if not (paths.src / "solution.py").exists():
        build_mod.build(paths)
    df, errors, warnings = solution.run_forecast(paths, issue_date, sites)
    out = out or paths.output / issue_date.isoformat() / "forecast.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    problems = schema.validate(df)
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} forecasts -> {out}")
    for w in warnings:
        print("WARNING", w, file=sys.stderr)
    for site, msg in errors:
        print(f"ERROR {site}: {msg}", file=sys.stderr)
    for p in problems:
        print(f"ERROR output: {p}", file=sys.stderr)
    return 0 if (allow_partial or not (errors or problems)) else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oshbocker_infer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["build", "check-assets", "fetch-assets", "check-sources", "manifest", "download", "predict", "run"])
    p.add_argument("--root", help="work root (default $WSF_ROOT or ~/wsf)")
    p.add_argument("--issue-date", type=_issue)
    p.add_argument("--sites", nargs="+")
    p.add_argument("--out", type=Path)
    p.add_argument("--from", dest="source", help="assets source directory or s3:// URI (fetch-assets)")
    p.add_argument("--sources", nargs="+", help="check-sources: only these probes")
    p.add_argument("--no-refresh", action="store_true", help="download: keep existing files of the forecast year")
    p.add_argument("--allow-partial", action="store_true", help="exit 0 even if some sites failed")
    a = p.parse_args(argv)
    paths = Paths.from_root(a.root)

    if a.command in ("download", "predict", "run") and not a.issue_date:
        p.error("--issue-date is required")

    if a.command == "check-sources":
        from . import check_sources

        return check_sources.report(check_sources.check_sources(only=a.sources))
    if a.command == "manifest":
        print(build_mod.write_manifest(build_mod.CORE, build_mod.CORE_MANIFEST), "core files")
        if paths.assets.is_dir():
            print(build_mod.write_manifest(paths.assets, build_mod.ASSET_MANIFEST), "asset files")
        return 0
    if a.command == "fetch-assets":
        paths.assets.mkdir(parents=True, exist_ok=True)
        if not a.source:
            p.error("--from is required")
        cmd = ["aws", "s3", "sync", a.source, str(paths.assets)] if a.source.startswith("s3://") else ["rsync", "-a", a.source.rstrip("/") + "/", str(paths.assets) + "/"]
        subprocess.run(cmd, check=True)
    if a.command in ("check-assets", "fetch-assets"):
        problems = build_mod.check_core() + build_mod.check_assets(paths)
        for pr in problems:
            print("PROBLEM", pr)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if a.command == "build":
        print("built", build_mod.build(paths))
        return 0
    if a.command in ("download", "run"):
        from . import download

        download.download(paths, a.issue_date, refresh=not a.no_refresh)
    if a.command in ("predict", "run"):
        if a.command == "run":
            build_mod.build(paths)
        return cmd_predict(paths, a.issue_date, a.sites, a.out, a.allow_partial)
    return 0


if __name__ == "__main__":
    sys.exit(main())
