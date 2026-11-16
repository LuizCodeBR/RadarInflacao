"""Central: qualidade, histórico, atomicidade, CSV e demonstração offline."""

import csv
import io
import json
import shutil
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest
from conftest import ROOT
from test_groups import GroupFakeSource
from test_pipeline import Source

from radar_inflacao import audit
from radar_inflacao.cli import main
from radar_inflacao.errors import RadarError, SourceError, ValidationError
from radar_inflacao.pipeline import GroupPipeline, Pipeline
from radar_inflacao.quality import build_quality
from radar_inflacao.quality_report import changes_csv_bytes, quality_csv_bytes
from radar_inflacao.simulation import prepare_demo
from radar_inflacao.storage import Repository


@pytest.fixture(scope="module")
def quality_template(tmp_path_factory):
    directory = tmp_path_factory.mktemp("quality-seed") / "data"
    repository = Repository(directory)
    Pipeline(repository, ROOT / "sample").demo()
    GroupPipeline(repository, ROOT / "sample/groups").demo()
    return directory


@pytest.fixture
def quality_repository(quality_template, tmp_path):
    directory = tmp_path / "quality"
    shutil.copytree(quality_template, directory)
    return Repository(directory)


def report(repository, **filters):
    return build_quality(repository.quality_snapshot(**filters))


def test_initial_import_checks_counts_and_explicit_absence(quality_repository):
    snapshot = report(quality_repository, kind="all")
    assert snapshot["total_changes"] == 3198  # 82*3 + 738*4, por campo incluído.
    assert not snapshot["truncated"]
    assert [item["grade"] for item in snapshot["datasets"]] == ["OK", "OK", "EMPTY"]
    assert [item["count"] for item in snapshot["datasets"]] == [82, 738, 0]
    assert "99 campos" in snapshot["datasets"][1]["checks"][1]["detail"]
    assert snapshot["datasets"][0]["checks"][3]["status"] == "INFO"
    assert "sem consulta agora" in snapshot["datasets"][0]["checks"][3]["detail"]
    assert all(r["kind"] == "ADDED" for r in snapshot["changes"])
    assert sum(r["new_value"] is None for r in snapshot["changes"]) == 99
    assert (
        len(
            list(
                csv.DictReader(
                    io.StringIO(quality_csv_bytes(snapshot).decode("utf-8-sig")), delimiter=";"
                )
            )
        )
        == 12
    )


def test_repeated_import_does_not_log_false_changes(quality_repository):
    before = quality_repository.quality_snapshot(kind="all")
    result = Pipeline(quality_repository, ROOT / "sample").demo()
    result_groups = GroupPipeline(quality_repository, ROOT / "sample/groups").demo()
    after = quality_repository.quality_snapshot(kind="all")
    assert result["change_fields"] == result_groups["change_fields"] == 0
    assert before["changes"] == after["changes"]
    assert after["datasets"][0]["latest_success"]["id"] == result["id"]


def test_changed_field_records_exact_values_and_lineage(
    quality_repository, sample_payload, metadata
):
    source = Source(sample_payload, metadata, changed=True)
    result = Pipeline(quality_repository, ROOT / "sample", source).update()
    snapshot = quality_repository.quality_snapshot()
    assert result["updated"] == result["change_fields"] == 1
    change = snapshot["changes"][0]
    assert change["period"] == "2026-10" and change["field"] == "monthly"
    assert change["new_value"] == Decimal("9.99")
    assert change["old_value"] != change["new_value"]
    assert change["run_id"] == result["id"]
    assert change["previous_run_id"] != change["run_id"]
    assert change["mode"] == "live" and change["raw_sha256"] == result["raw_sha256"]
    repeated = Pipeline(quality_repository, ROOT / "sample", source).update()
    assert repeated["change_fields"] == 0
    assert quality_repository.quality_snapshot()["total_changes"] == 1


def test_new_month_is_addition_not_change(quality_repository):
    from radar_inflacao.model import Observation
    from radar_inflacao.storage import utc_now

    observations = [Observation("2026-11", Decimal("0.1"), Decimal("1"), Decimal("2"))]
    with quality_repository.locked() as db:
        run = db.execute("SELECT id FROM ingestion LIMIT 1").fetchone()[0]
        db.execute("BEGIN TRANSACTION")
        audit.record_changes(
            db, "national", quality_repository.rows(db), observations, run, utc_now()
        )
        quality_repository.upsert(db, observations, run)
        db.execute("COMMIT")
    rows = quality_repository.quality_snapshot(start="2026-11", kind="all")["changes"]
    assert len(rows) == 3 and all(r["kind"] == "ADDED" for r in rows)
    assert all(r["old_value"] is None and r["previous_run_id"] is None for r in rows)


def test_history_and_values_roll_back_together(quality_repository, monkeypatch):
    before = quality_repository.quality_snapshot(kind="all")
    original = quality_repository.upsert_groups

    def fail(db, rows, run_id):
        original(db, rows[:1], run_id)
        raise RuntimeError("Falha antes do commit")

    monkeypatch.setattr(quality_repository, "upsert_groups", fail)
    with pytest.raises(RadarError):
        GroupPipeline(
            quality_repository, ROOT / "sample/groups", GroupFakeSource(changed=True)
        ).update()
    after = quality_repository.quality_snapshot(kind="all")
    assert before["changes"] == after["changes"]
    assert before["datasets"][1]["rows"] == after["datasets"][1]["rows"]
    assert after["datasets"][1]["latest_attempt"]["status"] == "FAILED"
    assert after["datasets"][1]["latest_attempt"]["stage"] == "PUBLISH"
    assert after["datasets"][1]["latest_success"] == before["datasets"][1]["latest_success"]


def test_record_history_failure_rolls_back_publication(quality_repository, monkeypatch):
    original = audit.record_changes
    before = quality_repository.quality_snapshot(kind="all")

    def fail(*args):
        original(*args)
        raise RuntimeError("Falha ao registrar histórico")

    monkeypatch.setattr(audit, "record_changes", fail)
    with pytest.raises(RadarError):
        GroupPipeline(
            quality_repository, ROOT / "sample/groups", GroupFakeSource(changed=True)
        ).update()
    after = quality_repository.quality_snapshot(kind="all")
    assert before["changes"] == after["changes"]
    assert before["datasets"][1]["rows"] == after["datasets"][1]["rows"]


def test_failure_after_metadata_shows_available_month_without_fake_publication(
    quality_repository, sample_payload, metadata
):
    payload = json.loads(metadata)
    payload["periodicidade"]["fim"] = "202611"

    class FailsAfterMetadata(Source):
        def observations(self, start, end):
            raise SourceError("Download indisponível")

    before = report(quality_repository)["datasets"][0]["latest_success"]
    with pytest.raises(SourceError):
        Pipeline(
            quality_repository,
            ROOT / "sample",
            FailsAfterMetadata(sample_payload, json.dumps(payload).encode()),
        ).update()
    item = report(quality_repository)["datasets"][0]
    assert item["latest_attempt"]["stage"] == "DOWNLOAD"
    assert item["latest_attempt"]["status"] == "FAILED"
    assert item["latest_success"] == before
    assert item["checks"][3]["status"] == "WARNING"
    assert "2026-11" in item["checks"][3]["detail"]
    assert item["end"] == "2026-10"


def test_invalid_metadata_does_not_confirm_availability(
    quality_repository, sample_payload, metadata
):
    payload = json.loads(metadata)
    payload["id"] = 999
    with pytest.raises(ValidationError):
        Pipeline(
            quality_repository,
            ROOT / "sample",
            Source(sample_payload, json.dumps(payload).encode()),
        ).update()
    item = report(quality_repository)["datasets"][0]
    assert item["reference"]["mode"] == "sample"
    assert item["latest_attempt"]["declared_end"] is None
    assert item["latest_attempt"]["stage"] == "METADATA"


@pytest.mark.parametrize(
    "query,code",
    [
        ("DELETE FROM observation WHERE period='2024-01-01'", "coverage"),
        ("DELETE FROM group_observation WHERE group_id='7170' AND period='2024-01-01'", "coverage"),
        ("UPDATE group_observation SET weight=-1 WHERE group_id='7170'", "values"),
        ("UPDATE group_observation SET twelve_month=NULL WHERE period='2024-01-01'", "values"),
        ("UPDATE group_ingestion SET raw_sha256='=1+1'", "provenance"),
    ],
)
def test_quality_explains_corruption_without_crashing(quality_repository, query, code):
    with quality_repository.locked() as db:
        db.execute(query)
    snapshot = report(quality_repository)
    assert any(
        c["code"] == code and c["status"] == "ERROR"
        for d in snapshot["datasets"]
        for c in d["checks"]
    )
    assert any(d["grade"] == "ERROR" for d in snapshot["datasets"])


def test_empty_database_reports_unknown_without_network(repository):
    snapshot = report(repository)
    assert [item["grade"] for item in snapshot["datasets"]] == ["EMPTY", "EMPTY", "EMPTY"]
    assert snapshot["changes"] == []
    assert quality_csv_bytes(snapshot).startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize(
    "filters",
    [
        {"dataset": "unknown"},
        {"kind": "=1"},
        {"start": "2024-13"},
        {"start": "2024-02", "end": "2024-01"},
        {"group_id": "7170"},
        {"dataset": "groups", "group_id": "9999"},
    ],
)
def test_invalid_filters_are_rejected(quality_repository, filters):
    with pytest.raises(ValidationError):
        quality_repository.quality_snapshot(**filters)


def test_filters_csv_negative_numbers_nulls_and_decimal_context(quality_repository):
    snapshot = quality_repository.quality_snapshot(
        dataset="groups", kind="ADDED", group_id="7625", start="2020-01", end="2020-01"
    )
    assert snapshot["total_changes"] == 4
    baseline = changes_csv_bytes(snapshot)
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = context.traps[Rounded] = True
        assert changes_csv_bytes(snapshot) == baseline
    records = list(csv.DictReader(io.StringIO(baseline.decode("utf-8-sig")), delimiter=";"))
    assert len(records) == 4
    assert all(r["Valor anterior (%)"] == "" for r in records)
    assert (
        next(r for r in records if r["Indicador"] == "Acumulado em 12 meses")["Valor novo (%)"]
        == ""
    )
    negative = quality_repository.quality_snapshot(
        dataset="groups", kind="ADDED", group_id="7625", start="2024-01", end="2024-01"
    )
    assert ";-0,65;" in changes_csv_bytes(negative).decode("utf-8-sig")


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "=1"),
        ("raw_sha256", "\t=1"),
        ("retrieved_at", "＠SUM(1)"),
        ("field", "=1"),
        ("mode", "unknown"),
        ("new_value", Decimal("NaN")),
        ("new_value", None),
        ("run_status", "FAILED"),
    ],
)
def test_changes_csv_refuses_hostile_or_invalid_fields(quality_repository, field, value):
    snapshot = quality_repository.quality_snapshot(
        dataset="national", kind="ADDED", start="2024-01", end="2024-01"
    )
    snapshot["changes"][0][field] = value
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)


def test_export_limit_never_silently_truncates(quality_repository):
    snapshot = quality_repository.quality_snapshot()
    snapshot["truncated"] = True
    with pytest.raises(ValidationError, match="10000"):
        changes_csv_bytes(snapshot)


def test_quality_csv_refuses_formula_in_detail(quality_repository):
    snapshot = report(quality_repository)
    snapshot["datasets"][0]["checks"][0]["detail"] = " =1+1"
    with pytest.raises(ValidationError):
        quality_csv_bytes(snapshot)


def test_cli_reports_and_exports_without_overwriting(quality_repository, tmp_path, capsys):
    args = ["--data-dir", str(quality_repository.directory)]
    assert main([*args, "quality"]) == 0
    assert len(json.loads(capsys.readouterr().out)["datasets"]) == 3
    output = tmp_path / "quality.csv"
    assert main([*args, "quality-export", "--output", str(output)]) == 0
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    capsys.readouterr()
    assert main([*args, "quality-export", "--output", str(output)]) == 2
    assert "já existe" in capsys.readouterr().out
    changes = tmp_path / "changes.csv"
    assert (
        main(
            [
                *args,
                "quality-export",
                "--report",
                "changes",
                "--kind",
                "ADDED",
                "--dataset",
                "groups",
                "--group",
                "7170",
                "--from",
                "2024-01",
                "--to",
                "2024-01",
                "--output",
                str(changes),
            ]
        )
        == 0
    )
    assert (
        len(
            list(
                csv.DictReader(io.StringIO(changes.read_text(encoding="utf-8-sig")), delimiter=";")
            )
        )
        == 4
    )


def test_simulation_is_isolated_idempotent_and_identified(tmp_path, quality_repository):
    shutil.copytree(ROOT / "sample", tmp_path / "sample")
    before = quality_repository.quality_snapshot(kind="all")
    demo = prepare_demo(tmp_path)
    snapshot = report(demo)
    assert snapshot["total_changes"] == 2
    assert all(r["mode"] == "simulation" for r in snapshot["changes"])
    assert "Simulação offline" in changes_csv_bytes(snapshot).decode("utf-8-sig")
    assert snapshot["datasets"][1]["latest_attempt"]["status"] == "FAILED"
    assert snapshot["datasets"][1]["checks"][3]["status"] == "INFO"
    again = prepare_demo(tmp_path).quality_snapshot()
    assert again["changes"] == snapshot["changes"]
    assert again["datasets"][0]["history"] == snapshot["datasets"][0]["history"]
    assert quality_repository.quality_snapshot(kind="all")["changes"] == before["changes"]
    assert main(["--data-dir", str(quality_repository.directory), "quality-demo"]) == 2


def test_simulation_refuses_existing_unidentified_directory(tmp_path):
    directory = tmp_path / ".cache/quality-demo"
    directory.mkdir(parents=True)
    (directory / "important.txt").write_text("preserve")
    with pytest.raises(ValidationError, match="não identificados"):
        prepare_demo(tmp_path)
    assert (directory / "important.txt").read_text() == "preserve"


def test_quality_view_offline_demo_filters_and_downloads(quality_repository, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    import radar_inflacao.quality_view as view

    shutil.copytree(ROOT / "sample", tmp_path / "sample")
    demo = prepare_demo(tmp_path)
    monkeypatch.setattr(view, "prepare_demo", lambda root: demo)
    monkeypatch.setenv("RADAR_DATA_DIR", str(quality_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("Qualidade e atualização").run()
    assert not app.exception
    assert len(app.get("download_button")) == 1
    app.toggle(key="quality_demo").set_value(True).run()
    assert not app.exception
    assert any("SIMULAÇÃO OFFLINE" in w.value for w in app.warning)
    assert len(app.get("download_button")) == 2
    assert all(button.proto.ignore_rerun for button in app.get("download_button"))
    table = next(d.value for d in app.dataframe if "Evento" in d.value.columns)
    assert len(table) == 2 and set(table["Modo"]) == {"Simulação offline"}
    key = next(s.key for s in app.selectbox if s.label == "Conjunto do histórico")
    app.selectbox(key=key).select("groups").run()
    assert len(next(d.value for d in app.dataframe if "Evento" in d.value.columns)) == 1
    start = next(t for t in app.text_input if t.label.startswith("Mês inicial"))
    start.set_value("2024-99").run()
    assert not app.exception
    assert any("Mês inválido" in error.value for error in app.error)


def test_schema_2_upgrade_preserves_rows_and_starts_without_invented_history(quality_repository):
    before = quality_repository.snapshot(include_groups=True)
    with quality_repository.locked() as db:
        for table in (
            "area_change",
            "area_observation",
            "area_dimension",
            "area_ingestion",
            "data_change",
            "audit_run",
            "audit_baseline",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("UPDATE schema_version SET version=2")
    snapshot = quality_repository.quality_snapshot(kind="all")
    assert [d["baseline"]["existing_rows"] for d in snapshot["datasets"]] == [82, 738, 0]
    assert snapshot["changes"] == []
    assert snapshot["datasets"][0]["rows"] == before["rows"]
    assert snapshot["datasets"][1]["rows"] == before["groups"]
    assert all(d["reference"] is None for d in snapshot["datasets"])
    assert all(d["checks"][3]["status"] == "UNKNOWN" for d in build_quality(snapshot)["datasets"])


def test_schema_3_migration_failure_is_atomic(quality_repository):
    with quality_repository.locked() as db:
        for table in (
            "area_change",
            "area_observation",
            "area_dimension",
            "area_ingestion",
            "data_change",
            "audit_run",
            "audit_baseline",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("UPDATE schema_version SET version=2")

        class FailMigration:
            def execute(self, sql, *args):
                if "CREATE TABLE data_change" in sql:
                    raise RuntimeError("Falha simulada de migração")
                return db.execute(sql, *args)

        with pytest.raises(RuntimeError, match="migração"):
            audit.migrate(FailMigration())
        assert db.execute("SELECT version FROM schema_version").fetchone() == (2,)
        tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
        assert not tables & {"data_change", "audit_baseline", "audit_run"}
        assert db.execute("SELECT count(*) FROM observation").fetchone() == (82,)
    assert quality_repository.quality_snapshot()["changes"] == []


def test_quality_export_invalid_filter_creates_no_file(quality_repository, tmp_path, capsys):
    destination = tmp_path / "invalid.csv"
    assert (
        main(
            [
                "--data-dir",
                str(quality_repository.directory),
                "quality-export",
                "--dataset",
                "national",
                "--group",
                "7170",
                "--output",
                str(destination),
            ]
        )
        == 2
    )
    assert not destination.exists()
    assert "ERROR" in capsys.readouterr().out


def test_history_read_limit_is_explicit(quality_repository, monkeypatch):
    monkeypatch.setattr(audit, "MAX_CHANGES", 2)
    snapshot = quality_repository.quality_snapshot(kind="all")
    assert len(snapshot["changes"]) == 2
    assert snapshot["total_changes"] == 3198 and snapshot["truncated"]
    with pytest.raises(ValidationError):
        changes_csv_bytes(snapshot)
