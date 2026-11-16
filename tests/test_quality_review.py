"""Revisão independente: falhas reproduzidas e contratos de segurança da central."""

import csv
import io
import json
import shutil
from copy import deepcopy
from uuid import uuid4

import pytest
from conftest import ROOT
from test_quality import quality_repository as quality_repository
from test_quality import quality_template as quality_template

from radar_inflacao.errors import ValidationError
from radar_inflacao.quality import build_quality
from radar_inflacao.quality_report import changes_csv_bytes, quality_csv_bytes
from radar_inflacao.simulation import prepare_demo


def read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def test_orphan_history_never_disappears_into_a_partial_csv(quality_repository):
    with quality_repository.locked() as db:
        db.execute("UPDATE data_change SET run_id=? WHERE dataset='national'", [str(uuid4())])
    snapshot = quality_repository.quality_snapshot(dataset="national", kind="ADDED")
    assert snapshot["total_changes"] == len(snapshot["changes"]) == 246
    assert build_quality(snapshot)["datasets"][0]["grade"] == "ERROR"
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


@pytest.mark.parametrize("status", ["FAILED", "INTERRUPTED", None])
def test_rows_attached_to_unsuccessful_run_are_not_certified(quality_repository, status):
    with quality_repository.locked() as db:
        db.execute("UPDATE ingestion SET status=?", [status])
    item = build_quality(quality_repository.quality_snapshot())["datasets"][0]
    assert item["grade"] == "ERROR"


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "unknown"),
        ("metadata_observed_at", None),
        ("checked_metadata_sha256", "not-a-hash"),
        ("declared_end", "2019-12"),
    ],
)
def test_invalid_availability_reference_is_not_approved(quality_repository, field, value):
    snapshot = quality_repository.quality_snapshot()
    snapshot["datasets"][0]["reference"][field] = value
    check = build_quality(snapshot)["datasets"][0]["checks"][3]
    assert check["status"] == "ERROR"


@pytest.mark.parametrize("mutation", ["count", "duplicate", "filter", "boolean_count"])
def test_csv_requires_complete_unique_filter_consistent_history(quality_repository, mutation):
    snapshot = quality_repository.quality_snapshot(
        dataset="national", kind="ADDED", start="2024-01", end="2024-01"
    )
    if mutation == "count":
        snapshot["total_changes"] += 1
    elif mutation == "duplicate":
        snapshot["changes"][1] = deepcopy(snapshot["changes"][0])
    elif mutation == "filter":
        snapshot["filters"]["start"] = "2024-02"
        snapshot["filters"]["end"] = "2024-02"
    else:
        snapshot["total_changes"] = True
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


@pytest.mark.parametrize(
    "marker",
    [
        {"simulation": "quality-v1", "complete": True},
        {"simulation": "quality-v1", "complete": 1},
    ],
)
def test_demo_marker_alone_does_not_certify_missing_database(tmp_path, marker):
    directory = tmp_path / ".cache/quality-demo"
    directory.mkdir(parents=True)
    (directory / "simulation.json").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValidationError):
        prepare_demo(tmp_path)
    assert not (directory / "radar.duckdb").exists()


def test_missing_audit_baseline_reports_domain_error(quality_repository):
    with quality_repository.locked() as db:
        db.execute("DELETE FROM audit_baseline WHERE dataset='national'")
    with pytest.raises(ValidationError):
        quality_repository.quality_snapshot()


def test_demo_cannot_be_used_as_primary_data_directory(tmp_path, monkeypatch):
    from radar_inflacao import cli

    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    directory = tmp_path / ".cache/quality-demo"
    monkeypatch.setenv("RADAR_DATA_DIR", str(directory))
    with pytest.raises(ValidationError):
        cli.components()
    with pytest.raises(ValidationError):
        cli.components(directory / "nested")


def test_quality_csv_validates_success_instead_of_only_its_timestamp(quality_repository):
    report = build_quality(quality_repository.quality_snapshot())
    report["datasets"][0]["latest_success"]["status"] = "FAILED"
    with pytest.raises(ValidationError):
        quality_csv_bytes(report)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity"])
def test_changed_csv_refuses_non_finite_before_decimal_comparison(quality_repository, value):
    from decimal import Decimal

    snapshot = quality_repository.quality_snapshot(
        dataset="national", kind="ADDED", start="2024-01", end="2024-01"
    )
    row = snapshot["changes"][0]
    snapshot["filters"]["kind"] = "all"
    row.update(
        kind="CHANGED",
        previous_run_id=str(uuid4()),
        previous_run_status="SUCCESS",
        old_value=Decimal(value),
    )
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


def test_quality_explains_mixed_invalid_modes_without_crash(quality_repository):
    snapshot = quality_repository.quality_snapshot()
    snapshot["datasets"][0]["rows"][0]["mode"] = None
    report = build_quality(snapshot)
    assert report["datasets"][0]["grade"] == "ERROR"
    with pytest.raises(ValidationError):
        quality_csv_bytes(report)


@pytest.mark.parametrize("previous", ["missing", "same", "failed"])
def test_previous_run_must_be_distinct_and_successful(
    quality_repository, sample_payload, metadata, previous
):
    from test_pipeline import Source

    from radar_inflacao.pipeline import Pipeline

    run = Pipeline(
        quality_repository, ROOT / "sample", Source(sample_payload, metadata, changed=True)
    ).update()["id"]
    with quality_repository.locked() as db:
        if previous == "failed":
            old_id = db.execute(
                "SELECT previous_run_id FROM data_change WHERE kind='CHANGED'"
            ).fetchone()[0]
            db.execute("UPDATE ingestion SET status='FAILED' WHERE id=?", [old_id])
        else:
            db.execute(
                "UPDATE data_change SET previous_run_id=? WHERE kind='CHANGED'",
                [run if previous == "same" else str(uuid4())],
            )
    snapshot = quality_repository.quality_snapshot()
    assert build_quality(snapshot)["datasets"][0]["grade"] == "ERROR"
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


def test_history_day_is_not_silently_normalized(quality_repository):
    with quality_repository.locked() as db:
        db.execute("UPDATE data_change SET period='2024-01-02' WHERE period='2024-01-01'")
    snapshot = quality_repository.quality_snapshot(kind="ADDED")
    assert build_quality(snapshot)["datasets"][0]["grade"] == "ERROR"
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


@pytest.mark.parametrize("payload", ["{", "x" * 2049])
def test_malformed_demo_marker_is_explained_and_preserved(tmp_path, payload):
    directory = tmp_path / ".cache/quality-demo"
    directory.mkdir(parents=True)
    marker = directory / "simulation.json"
    marker.write_text(payload, encoding="utf-8")
    with pytest.raises(ValidationError):
        prepare_demo(tmp_path)
    assert marker.read_text(encoding="utf-8") == payload


@pytest.mark.parametrize("name", ["simulation.json", "radar.duckdb", "../quality-demo.lock"])
def test_demo_refuses_hardlinks_without_modifying_target(tmp_path, name):
    import os

    directory = tmp_path / ".cache/quality-demo"
    directory.mkdir(parents=True)
    target = tmp_path / "preserve.txt"
    target.write_text("preserve", encoding="utf-8")
    os.link(target, directory / name)
    with pytest.raises(ValidationError):
        prepare_demo(tmp_path)
    assert target.read_text(encoding="utf-8") == "preserve"


def test_cli_demo_directory_allows_reports_but_refuses_update(tmp_path, monkeypatch, capsys):
    from radar_inflacao import cli

    shutil.copytree(ROOT / "sample", tmp_path / "sample")
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    repository = prepare_demo(tmp_path)
    before = repository.quality_snapshot()
    args = ["--data-dir", str(repository.directory)]
    assert cli.main([*args, "quality"]) == 0
    capsys.readouterr()
    assert cli.main([*args, "update"]) == 2
    assert "demonstração" in capsys.readouterr().out
    after = repository.quality_snapshot()
    assert after["changes"] == before["changes"]
    assert after["datasets"][0]["history"] == before["datasets"][0]["history"]


def test_availability_and_last_success_survive_more_than_twenty_failures(quality_repository):
    from radar_inflacao import audit

    before = quality_repository.quality_snapshot()["datasets"][0]
    with quality_repository.locked() as db:
        for _ in range(21):
            run = str(uuid4())
            db.execute(
                """INSERT INTO ingestion(id,started_at,finished_at,mode,status,error)
                VALUES(?,current_timestamp,current_timestamp,'live','FAILED','Falha simulada')""",
                [run],
            )
            audit.start_run(db, "national", run)
    after = quality_repository.quality_snapshot()["datasets"][0]
    assert len(after["history"]) == 20
    assert after["latest_attempt"]["status"] == "FAILED"
    assert after["latest_success"] == before["latest_success"]
    assert after["reference"] == before["reference"]


@pytest.mark.parametrize(
    "payload", ["=1+1", " +1", "\t=1", "\r=1", "\n=1", "＠SUM(1)", "＝1", "－1", "＋1"]
)
def test_quality_error_detail_cannot_inject_formulas(quality_repository, payload):
    report = build_quality(quality_repository.quality_snapshot())
    report["datasets"][0]["latest_attempt"]["error"] = payload
    with pytest.raises(ValidationError):
        quality_csv_bytes(report)


def test_csv_quotes_do_not_create_additional_cells(quality_repository):
    report = build_quality(quality_repository.quality_snapshot())
    detail = 'Falha ";=1+1; documento'
    report["datasets"][0]["checks"][0]["detail"] = detail
    records = read_csv(quality_csv_bytes(report))
    assert len(records) == 8
    assert records[0]["Detalhe"] == detail
    assert all(None not in row for row in records)


def test_quality_view_handles_invalid_metadata_without_traceback(quality_repository, monkeypatch):
    from streamlit.testing.v1 import AppTest

    with quality_repository.locked() as db:
        db.execute("UPDATE audit_run SET metadata_observed_at=NULL WHERE dataset='national'")
    monkeypatch.setenv("RADAR_DATA_DIR", str(quality_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("Qualidade e atualização").run()
    assert not app.exception
    assert any("Relatório indisponível" in e.value for e in app.error)
    assert not app.get("download_button")
    assert any("Problema identificado" in m.value for m in app.markdown)


def test_dashboard_rejects_demo_as_primary_without_traceback(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(ROOT / ".cache/quality-demo"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not app.exception
    assert any("não pode ser a base principal" in e.value for e in app.error)


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_national_publication_keeps_quality_and_history_atomic(quality_repository, finish):
    import subprocess
    import sys

    from test_group_review import _line

    from radar_inflacao.errors import BusyError

    before = quality_repository.quality_snapshot(kind="all")
    exports = (quality_csv_bytes(build_quality(before)), changes_csv_bytes(before))
    script = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from test_pipeline import Source
from radar_inflacao.storage import Repository
from radar_inflacao.pipeline import Pipeline
sample=Path(sys.argv[2]).parent/'sample'
class PausingRepository(Repository):
    def upsert(self, db, rows, run_id):
        counts=super().upsert(db,rows,run_id)
        print('UNCOMMITTED',flush=True)
        sys.stdin.readline()
        return counts
source=Source(json.loads((sample/'ibge-1737.json').read_bytes()),
              (sample/'metadata-1737.json').read_bytes(),changed=True)
result=Pipeline(PausingRepository(Path(sys.argv[1])),sample,source).update()
print(result['status'],flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(quality_repository.directory), str(ROOT / "tests")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _line(process) == "UNCOMMITTED"
        with pytest.raises(BusyError):
            quality_repository.quality_snapshot()
        assert quality_csv_bytes(build_quality(before)) == exports[0]
        assert changes_csv_bytes(before) == exports[1]
        if finish == "commit":
            output, error = process.communicate("\n", timeout=30)
            assert process.returncode == 0 and "SUCCESS" in output, error
        else:
            process.kill()
            process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)
    after = quality_repository.quality_snapshot(kind="all")
    if finish == "crash":
        assert after["changes"] == before["changes"]
        assert after["datasets"][0]["rows"] == before["datasets"][0]["rows"]
        assert after["datasets"][0]["latest_attempt"]["status"] == "INTERRUPTED"
    else:
        assert after["total_changes"] == before["total_changes"] + 1
        assert after["datasets"][0]["latest_attempt"]["status"] == "SUCCESS"
    assert after["datasets"][1]["rows"] == before["datasets"][1]["rows"]
    assert quality_csv_bytes(build_quality(after))


def test_two_quality_exports_never_overwrite_or_mix_bytes(quality_repository, tmp_path):
    import subprocess
    import sys

    from test_group_review import _line

    snapshot = quality_repository.quality_snapshot(kind="ADDED")
    payloads = [quality_csv_bytes(build_quality(snapshot)), changes_csv_bytes(snapshot)]
    destination = tmp_path / "race.csv"
    script = r"""
import sys
from pathlib import Path
from radar_inflacao.report import publish_csv
data=Path(sys.argv[2]).read_bytes()
print('READY',flush=True)
sys.stdin.readline()
try:
    publish_csv(Path(sys.argv[1]),data)
    print('PUBLISHED',flush=True)
except FileExistsError:
    print('EXISTS',flush=True)
"""
    processes = []
    try:
        for index, payload in enumerate(payloads):
            source = tmp_path / f"payload-{index}.csv"
            source.write_bytes(payload)
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", script, str(destination), str(source)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        assert all(_line(p) == "READY" for p in processes)
        for p in processes:
            p.stdin.write("\n")
            p.stdin.flush()
        results = [p.communicate(timeout=30) for p in processes]
        assert all(p.returncode == 0 for p in processes), results
        assert sorted(out.strip() for out, _ in results) == ["EXISTS", "PUBLISHED"]
        assert destination.read_bytes() in payloads
        assert not list(tmp_path.glob(".radar-csv-*"))
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=15)


def test_concurrent_demo_preparation_is_exclusive_and_crash_is_preserved(tmp_path):
    import subprocess
    import sys

    from test_group_review import _line

    from radar_inflacao.errors import BusyError

    shutil.copytree(ROOT / "sample", tmp_path / "sample")
    script = r"""
import sys
from pathlib import Path
from radar_inflacao.pipeline import Pipeline
from radar_inflacao.simulation import prepare_demo
original=Pipeline.demo
def pause(self):
    result=original(self)
    print('PREPARING',flush=True)
    sys.stdin.readline()
    return result
Pipeline.demo=pause
prepare_demo(Path(sys.argv[1]))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _line(process) == "PREPARING"
        with pytest.raises(BusyError):
            prepare_demo(tmp_path)
        process.kill()
        process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)
    directory = tmp_path / ".cache/quality-demo"
    marker = (directory / "simulation.json").read_bytes()
    database = (directory / "radar.duckdb").read_bytes()
    with pytest.raises(ValidationError, match="incompleta"):
        prepare_demo(tmp_path)
    assert (directory / "simulation.json").read_bytes() == marker
    assert (directory / "radar.duckdb").read_bytes() == database
