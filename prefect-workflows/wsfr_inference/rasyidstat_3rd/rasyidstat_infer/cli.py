"""CLI: python -m rasyidstat_infer <command> [--root DIR]

    build            assemble <root>/rasyidstat_3rd/build/src from core/ + patches/ + assets/
    check-assets     verify assets/ against assets.sha256 (and core/ against core.sha256)
    fetch-assets     copy assets from a shared directory or s3:// URI, then verify
    check-sources    ping every external endpoint and verify the response shape (--sources to pick probes); exit 1 on failure
    manifest         (maintainers) rewrite core.sha256 / assets.sha256
    download         fetch all inputs for --issue-date (--sources to pick some) into downloads/ and data/
    preprocess       reduce downloads/ to the feature caches in preprocessed/
    predict          forecast every site for --issue-date -> output/<issue_date>/forecast.csv
    run              build + download + preprocess + predict
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


def cmd_predict(paths: Paths, issue_date: date, sites, out: Path | None, allow_partial: bool, strict: bool) -> int:
    from . import solution

    if not paths.src.exists():  # the core has no top-level solution.py; rebuilding here would delete the cwd set by engine.bootstrap
        build_mod.build(paths)
    df, errors, warnings = solution.predict(paths, issue_date, sites, strict)
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
    p = argparse.ArgumentParser(prog="rasyidstat_infer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["build", "check-assets", "fetch-assets", "check-sources", "manifest", "download", "preprocess", "predict", "run"])
    p.add_argument("--root", help="work root (default $WSF_ROOT or ~/wsf)")
    p.add_argument("--issue-date", type=_issue)
    p.add_argument("--sites", nargs="+")
    p.add_argument("--out", type=Path)
    p.add_argument("--from", dest="source", help="assets source directory or s3:// URI (fetch-assets)")
    p.add_argument("--sources", nargs="+", help="download / preprocess / check-sources: only these steps")
    p.add_argument("--strict", action="store_true", help="fail if any variant has to be left out (default: leave it out and warn)")
    p.add_argument("--allow-partial", action="store_true", help="exit 0 even if some sites failed")
    a = p.parse_args(argv)
    paths = Paths.from_root(a.root)

    if a.command in ("download", "preprocess", "predict", "run") and not a.issue_date:
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
    if a.command == "run":
        build_mod.build(paths)
    if a.command in ("download", "run"):
        from . import download

        if a.command == "download" and not paths.src.exists():
            build_mod.build(paths)
        download.download(paths, a.issue_date, a.sources, a.strict)
    if a.command in ("preprocess", "run"):
        from . import preprocess

        if not paths.src.exists():
            build_mod.build(paths)
        preprocess.preprocess(paths, a.issue_date, a.sources if a.command == "preprocess" else None)
    if a.command in ("predict", "run"):
        return cmd_predict(paths, a.issue_date, a.sites, a.out, a.allow_partial, a.strict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
