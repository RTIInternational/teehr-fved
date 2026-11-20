from datetime import date, datetime, timezone
import logging
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from workflows.models import wsf_utils as wsf


@pytest.fixture
def forecast(tmp_path):
    path = tmp_path / "forecast.csv"
    pd.DataFrame([{
        "site_id": "pecos_r_nr_pecos", "issue_date": "2026-03-01",
        "volume_10": 1.0, "volume_50": 2.0, "volume_90": 3.0,
        "model_version": "test_v1",
    }]).to_csv(path, index=False)
    return path


def test_issue_dates():
    assert wsf.resolve_issue_date("2026-03-05") == date(2026, 3, 5)
    scheduled = datetime(2026, 7, 22, 8, tzinfo=timezone.utc)
    assert wsf.resolve_issue_date(None, scheduled, True) == date(2026, 7, 22)
    assert wsf.resolve_issue_date("2026-01-08", scheduled, True) == date(2026, 1, 8)
    for invalid in (None, "2026-08-01", "2026-11-10", "20260301"):
        with pytest.raises(ValueError):
            wsf.resolve_issue_date(invalid)
    with pytest.raises(ValueError):
        wsf.resolve_issue_date(None, datetime(2026, 1, 2, tzinfo=timezone.utc), True)
    with pytest.raises(ValueError):
        wsf.resolve_issue_date(None, datetime(2026, 1, 1), True)
    with pytest.raises(ValueError):
        wsf.resolve_issue_date(None, scheduled, False)


def test_site_metadata_without_warehouse_mapping():
    for solution in wsf.MODEL_PACKAGES:
        mapping = wsf.read_model_sites(solution)
        assert len(mapping) == 26
        metadata_path = "static/raw/metadata.csv" if solution == "rasyidstat_3rd" else "static/metadata.csv"
        metadata = pd.read_csv(wsf.model_directory(solution) / metadata_path)
        assert set(metadata.site_id) == set(mapping)
        for record in metadata.to_dict("records"):
            assert mapping[record["site_id"]]["season_start_month"] == record["season_start_month"]
            assert mapping[record["site_id"]]["season_end_month"] == record["season_end_month"]
    assert len(wsf.eligible_sites(date(2026, 3, 1))) == 26
    assert len(wsf.eligible_sites(date(2026, 7, 1))) == 25
    for sites in ([], ["unknown"], ["pecos_r_nr_pecos"] * 2, ["detroit_lake_inflow"]):
        with pytest.raises(ValueError):
            wsf.eligible_sites(date(2026, 7, 1), sites)


def test_forecast_contract_preserves_model_sites_and_kaf(forecast):
    frame = wsf.validate_forecast(forecast, date(2026, 3, 1), ["pecos_r_nr_pecos"])
    assert frame.site_id.tolist() == ["pecos_r_nr_pecos"]
    assert frame.volume_10.tolist() == [1.0]
    assert "location_id" not in frame.columns


@pytest.mark.parametrize("column,value", [
    ("issue_date", "2026-03-02"), ("volume_10", -1),
    ("volume_90", float("inf")), ("volume_50", float("nan")),
    ("volume_10", 99), ("model_version", ""),
    ("model_version", "test_partial3of9"), ("site_id", "unknown"),
])
def test_invalid_forecasts(forecast, column, value):
    frame = pd.read_csv(forecast)
    frame[column] = value
    frame.to_csv(forecast, index=False)
    with pytest.raises(ValueError):
        wsf.validate_forecast(forecast, date(2026, 3, 1), ["pecos_r_nr_pecos"])


def test_partial_is_explicit(forecast):
    frame = pd.read_csv(forecast).assign(model_version="test_partial3of9")
    frame.to_csv(forecast, index=False)
    assert len(wsf.validate_forecast(forecast, date(2026, 3, 1), ["pecos_r_nr_pecos"], False)) == 1
    with pytest.raises(ValueError):
        wsf.validate_forecast(forecast, date(2026, 3, 1), ["pecos_r_nr_pecos", "animas_r_at_durango"], False)


def test_forecast_does_not_require_existing_warehouse_location(forecast):
    frame = pd.read_csv(forecast).assign(site_id="american_river_folsom_lake")
    frame.to_csv(forecast, index=False)
    assert len(wsf.validate_forecast(forecast, date(2026, 3, 1), ["american_river_folsom_lake"])) == 1


def test_asset_integrity(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    weight = assets / "model.txt"
    weight.write_text("model")
    manifest = tmp_path / "assets.sha256"
    manifest.write_text(f"{wsf.file_digest(weight)}  model.txt\n")
    wsf.verify_assets(assets, manifest)
    weight.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        wsf.verify_assets(assets, manifest)
    manifest.write_text("a" * 64 + "  ../unsafe\n")
    with pytest.raises(ValueError, match="Unsafe"):
        wsf.manifest_files(manifest)


def test_persistent_lock(tmp_path):
    with wsf.solution_lock(tmp_path, "ckua_2nd"):
        with pytest.raises(RuntimeError, match="cache lock"):
            with wsf.solution_lock(tmp_path, "ckua_2nd"):
                pytest.fail("overlapping run acquired lock")
    with wsf.solution_lock(tmp_path, "ckua_2nd"):
        pass


def test_subprocess_failure_and_redaction(tmp_path):
    log = tmp_path / "stage.log"
    with pytest.raises(RuntimeError, match="exited with code 2"):
        wsf.run_command(
            [sys.executable, "-c", "import os; print(os.environ['CDSAPI_KEY']); raise SystemExit(2)", "predict"],
            tmp_path, {"CDSAPI_KEY": "secret-value"}, log, 10, logging.getLogger(__name__),
        )
    assert "secret-value" not in log.read_text()
    assert "[REDACTED]" in log.read_text()


def test_subprocess_timeout(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        wsf.run_command(
            [sys.executable, "-c", "import threading; threading.Event().wait()", "download"],
            tmp_path, {}, tmp_path / "timeout.log", 1, logging.getLogger(__name__),
        )


def test_s3_uris():
    assert wsf.s3_location("s3://bucket/prefix/") == ("bucket", "prefix")
    for uri in ("", "https://bucket/prefix", "s3:///prefix", "s3://bucket/prefix?key=value"):
        with pytest.raises(ValueError):
            wsf.s3_location(uri)


def test_stage_assets_is_verified_and_reused(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    weight = package / "model.txt"
    weight.write_text("model")
    (package / "assets.sha256").write_text(f"{wsf.file_digest(weight)}  model.txt\n")
    monkeypatch.setattr(wsf, "model_directory", lambda solution: package)
    downloads = []

    class Client:
        def download_file(self, bucket, key, destination):
            downloads.append((bucket, key))
            Path(destination).write_text("model")

    cache = tmp_path / "cache"
    assets = wsf.stage_assets("ckua_2nd", "s3://bucket/ckua", cache, Client())
    assert downloads == [("bucket", "ckua/model.txt")]
    assert wsf.stage_assets("ckua_2nd", "s3://bucket/ckua", cache, Client()) == assets
    assert len(downloads) == 1
    (assets / "model.txt").write_text("corrupt")
    with pytest.raises(ValueError, match="changed"):
        wsf.stage_assets("ckua_2nd", "s3://bucket/ckua", cache, Client())


def test_archive_uploads_completion_record_last(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "run.json").write_text('{}')
    (directory / "forecast.csv").write_text("original model output")
    uploads = []

    class Client:
        def upload_file(self, source, bucket, key):
            uploads.append((bucket, key, Path(source).read_text()))

    assert wsf.archive_run(directory, "s3://bucket/runs/id", Client()) == "s3://bucket/runs/id"
    assert uploads[-1][1] == "runs/id/run.json"
    assert uploads[0][2] == "original model output"


@pytest.mark.parametrize("solution", list(wsf.MODEL_PACKAGES))
@pytest.mark.parametrize("failure", [False, True])
def test_execution_flow_without_warehouse(tmp_path, monkeypatch, solution, failure):
    pytest.importorskip("prefect")
    from types import SimpleNamespace
    from uuid import uuid4
    from workflows.models import wsf_forecasts as flows

    context = SimpleNamespace(flow_run=SimpleNamespace(
        id=uuid4(), auto_scheduled=True,
        expected_start_time=datetime(2026, 3, 1, 8, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr(flows, "get_run_context", lambda: context)
    monkeypatch.setattr(flows, "get_run_logger", lambda: logging.getLogger(__name__))
    monkeypatch.setattr(flows, "model_environment", lambda *args: {})
    monkeypatch.setattr(wsf, "source_digest", lambda: "revision")
    assets = tmp_path / "assets"
    assets.mkdir()
    monkeypatch.setattr(flows, "prepare_assets", lambda *args: assets)
    calls = []
    archives = []

    def execute(command, cwd, env, log_path, timeout):
        calls.append(command)
        assert command[0] == sys.executable
        if command[3] == "predict":
            out = Path(command[command.index("--out") + 1])
            pd.DataFrame([{
                "site_id": "american_river_folsom_lake", "issue_date": "2026-03-01",
                "volume_10": 1, "volume_50": 2, "volume_90": 3, "model_version": "test_v1",
            }]).to_csv(out, index=False)
            if failure:
                raise RuntimeError("Model stage predict exited with code 2")

    monkeypatch.setattr(flows, "execute_stage", execute)
    monkeypatch.setattr(flows, "publish_run", lambda path, uri: archives.append(uri))
    parameters = dict(
        solution=solution, sites=["american_river_folsom_lake"],
        assets_s3_uri="s3://bucket/assets", output_s3_uri="s3://bucket/outputs",
        cache_dir=str(tmp_path), model_python=sys.executable,
    )
    if failure:
        import json

        with pytest.raises(RuntimeError, match="exited with code 2"):
            flows.run_wsf_inference.fn(**parameters)
        manifests = list((tmp_path / "runs").rglob("run.json"))
        assert len(manifests) == 1
        assert json.loads(manifests[0].read_text())["status"] == "failed"
        assert len(archives) == 1
        return
    result = flows.run_wsf_inference.fn(**parameters)
    assert result["status"] == "succeeded"
    assert result["units"] == "KAF"
    assert result["issue_date"] == "2026-03-01"
    assert len(archives) == 1
    assert [command[3] for command in calls] == (
        ["check-assets", "build", "download", "preprocess", "predict"]
        if solution == "rasyidstat_3rd" else ["check-assets", "build", "download", "predict"]
    )
    assert "--allow-partial" not in calls[-1]


@pytest.mark.parametrize("filename", ["prefect-local.yaml", "prefect-remote.yaml"])
def test_wsf_deployments_and_schedule(filename):
    yaml = pytest.importorskip("yaml")
    croniter = pytest.importorskip("croniter").croniter
    root = Path(__file__).resolve().parents[2]
    document = yaml.safe_load((root / filename).read_text())
    deployments = [item for item in document["deployments"] if item["name"].startswith("wsf-inference-")]
    assert len(deployments) == 3
    assert {item["parameters"]["solution"] for item in deployments} == set(wsf.MODEL_PACKAGES)
    for item in deployments:
        assert "issue_date" not in item["parameters"]
        assert item["concurrency_limit"]["limit"] == 1
        variables = item["work_pool"]["job_variables"]
        assert variables["image"] == "{{ $PREFECT_WSF_IMAGE }}"
        assert "AWS_REGION" in variables["env"]
        assert variables["env"]["WSF_ASSETS_S3_URI"] == "{{ $WSF_ASSETS_S3_URI }}"
        assert variables["active_deadline_seconds"] > 10800
        schedule = item["schedule"]
        assert schedule["timezone"] == "UTC"
        assert schedule["active"] is False
        cursor = croniter(schedule["cron"], datetime(2026, 1, 1, tzinfo=timezone.utc))
        dates = [cursor.get_next(datetime) for _ in range(29)]
        assert [(stamp.month, stamp.day, stamp.hour) for stamp in dates[:28]] == [
            (month, day, 8) for month in range(1, 8) for day in (1, 8, 15, 22)
        ]
        assert dates[28].year == 2027


def test_secret_loader_manifest_matches_script():
    import ast

    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parents[2] / "manifests"
    manifest = yaml.safe_load((root / "load-secrets.yaml").read_text())
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert ast.dump(ast.parse(container["command"][-1])) == ast.dump(ast.parse((root / "load_secrets.py").read_text()))
    for variable in ("CDSAPI_URL", "CDSAPI_KEY"):
        entry = next(item for item in container["env"] if item["name"] == variable)
        assert entry["valueFrom"]["secretKeyRef"]["optional"] is True