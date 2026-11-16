import copy
import csv
import io
import json
import subprocess
import sys
from decimal import Decimal

import duckdb
import pytest
from conftest import ROOT

from radar_inflacao.errors import BusyError, RadarError, SourceError, ValidationError
from radar_inflacao.groups import (
    GROUPS,
    filter_group_rows,
    group_comparisons,
    group_ranking,
    parse_group_observations,
    validate_group_metadata,
)
from radar_inflacao.model import periods
from radar_inflacao.pipeline import GroupPipeline
from radar_inflacao.report import group_comparison_csv_bytes, group_csv_bytes
from radar_inflacao.source import GROUP_API, Download, GroupSource, group_data_url
from radar_inflacao.storage import Repository

SAMPLE = ROOT / "sample/groups"


@pytest.fixture
def group_pipeline(repository):
    return GroupPipeline(repository, SAMPLE)


@pytest.fixture
def group_rows(group_pipeline, repository):
    group_pipeline.demo()
    return repository.snapshot(include_groups=True)["groups"]


def payload():
    return json.loads((SAMPLE / "ibge-7060.json").read_bytes())


class GroupFakeSource:
    def __init__(self, *, corrupt=False, changed=False):
        self.requested = None
        self.corrupt = corrupt
        self.changed = changed

    def metadata(self):
        return Download((SAMPLE / "metadata-7060.json").read_bytes(), GROUP_API + "/metadados")

    def observations(self, start, end):
        self.requested = (start, end)
        data = payload()
        for variable in data:
            if variable["id"] == "2265" and start >= "2020-12":
                variable["unidade"] = "%"
            for result in variable["resultados"]:
                result["series"][0]["serie"] = {
                    k: v
                    for k, v in result["series"][0]["serie"].items()
                    if start.replace("-", "") <= k <= end.replace("-", "")
                }
        if self.changed:
            data[0]["resultados"][0]["series"][0]["serie"]["202610"] = "9.99"
        if self.corrupt:
            data[0]["resultados"].pop()
        return Download(json.dumps(data).encode(), group_data_url(start, end))


def test_sample_contract_and_historical_nulls():
    raw = (SAMPLE / "ibge-7060.json").read_bytes()
    rows = parse_group_observations(raw, periods("2020-01", "2026-10"))
    assert len(rows) == 738
    assert sum(r.twelve_month is None for r in rows) == 99
    january = next(r for r in rows if r.period == "2024-01" and r.group_id == "7170")
    assert january.monthly == Decimal("1.38")
    assert next(r for r in rows if r.period == "2024-01" and r.group_id == "7625").monthly < 0
    assert validate_group_metadata((SAMPLE / "metadata-7060.json").read_bytes()) == "2026-10"


@pytest.mark.parametrize(
    "change",
    [
        "missing_group",
        "duplicate_group",
        "unknown_group",
        "wrong_class",
        "wrong_region",
        "missing_month",
        "missing_monthly",
        "unexpected_null",
        "negative_weight",
        "weight_total",
        "unit",
        "duplicate_variable",
    ],
)
def test_corrupt_group_batches_fail_closed(change):
    data = payload()
    target = data[0]["resultados"][0]
    if change == "missing_group":
        data[0]["resultados"].pop()
    elif change == "duplicate_group":
        data[0]["resultados"][1] = copy.deepcopy(target)
    elif change == "unknown_group":
        target["classificacoes"][0]["categoria"] = {"9999": "1.Other"}
    elif change == "wrong_class":
        target["classificacoes"][0]["id"] = "999"
    elif change == "wrong_region":
        target["series"][0]["localidade"]["id"] = "2"
    elif change == "missing_month":
        del target["series"][0]["serie"]["202401"]
    elif change == "missing_monthly":
        target["series"][0]["serie"]["202401"] = "..."
    elif change == "unexpected_null":
        data[2]["resultados"][0]["series"][0]["serie"]["202401"] = "..."
    elif change == "negative_weight":
        data[3]["resultados"][0]["series"][0]["serie"]["202401"] = "-1"
    elif change == "weight_total":
        data[3]["resultados"][0]["series"][0]["serie"]["202401"] = "99"
    elif change == "unit":
        data[0]["unidade"] = "R$"
    else:
        data[1]["id"] = "63"
    with pytest.raises(ValidationError):
        parse_group_observations(json.dumps(data).encode(), periods("2020-01", "2026-10"))


@pytest.mark.parametrize("change", ["table", "category", "unit", "territory"])
def test_metadata_changes_are_rejected(change):
    data = json.loads((SAMPLE / "metadata-7060.json").read_bytes())
    if change == "table":
        data["id"] = 1737
    elif change == "category":
        category = next(c for c in data["classificacoes"][0]["categorias"] if c["id"] == 7170)
        category["nome"] = "Renamed"
    elif change == "unit":
        data["variaveis"][0]["unidade"] = ""
    else:
        data["nivelTerritorial"]["Administrativo"] = ["N6"]
    with pytest.raises(ValidationError):
        validate_group_metadata(json.dumps(data).encode())


def test_idempotency_incremental_revision_and_separate_histories(group_pipeline, repository):
    first, second = group_pipeline.demo(), group_pipeline.demo()
    assert first["inserted"] == 738 and second["unchanged"] == 738
    source = GroupFakeSource(changed=True)
    changed = GroupPipeline(repository, SAMPLE, source).update()
    assert source.requested == ("2024-11", "2026-10")
    assert changed["rows"] == 216 and changed["updated"] == 1
    snapshot = repository.snapshot(include_groups=True)
    assert len(snapshot["groups"]) == 738
    assert len(snapshot["groups_history"]) == 3 and snapshot["history"] == []
    assert {r["mode"] for r in snapshot["groups"]} == {"sample", "live"}
    with pytest.raises(ValidationError, match="não substitui"):
        group_pipeline.demo()


def test_invalid_update_and_partial_database_write_preserve_both_datasets(
    group_rows, pipeline, repository, monkeypatch
):
    pipeline.demo()
    before = repository.snapshot(include_groups=True)
    with pytest.raises(ValidationError):
        GroupPipeline(repository, SAMPLE, GroupFakeSource(corrupt=True)).update()
    assert repository.snapshot(include_groups=True)["groups"] == before["groups"]
    original = repository.upsert_groups

    def fail(db, rows, run_id):
        original(db, rows[:1], run_id)
        raise RuntimeError("Before commit")

    monkeypatch.setattr(repository, "upsert_groups", fail)
    with pytest.raises(RadarError):
        GroupPipeline(repository, SAMPLE, GroupFakeSource(changed=True)).update()
    after = repository.snapshot(include_groups=True)
    assert after["groups"] == before["groups"] and after["rows"] == before["rows"]
    assert after["groups_history"][0][4] == "FAILED"


def test_filters_ranking_and_comparison_preserve_group_identity(group_rows):
    codes = ["7170", "7625"]
    selected = filter_group_rows(group_rows, codes, "2024-01", "2024-03")
    assert len(selected) == 6
    ranking = group_ranking(group_rows, list(GROUPS), "2024-01")
    assert ranking[0]["group_id"] == "7170"
    assert ranking[-1]["group_id"] == "7625"
    comparisons = group_comparisons(group_rows, codes, "2024-01", "2024-03", "2023-01", "2023-03")
    assert comparisons["7170"].a.monthly == Decimal("0.53")
    assert comparisons["7625"].a.monthly != comparisons["7170"].a.monthly
    early = group_comparisons(group_rows, codes, "2020-01", "2020-03", "2020-04", "2020-06")
    assert early["7170"].a.twelve_month is None
    assert early["7170"].measures[3].difference is None


@pytest.mark.parametrize("codes", [[], ["999"], ["7170", "7170"]])
def test_invalid_selection_is_clear(group_rows, codes):
    with pytest.raises(ValidationError):
        filter_group_rows(group_rows, codes, "2024-01", "2024-03")


def test_csv_identity_provenance_missing_and_comparison(group_rows):
    selected = filter_group_rows(group_rows, ["7170", "7625"], "2020-01", "2020-01")
    raw = group_csv_bytes(selected)
    assert raw.startswith(b"\xef\xbb\xbf")
    records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert len(records) == 2
    assert records[0]["Grupo"] == GROUPS["7170"]
    assert records[0]["Acumulado 12 meses (%)"] == ""
    assert records[0]["Origem"] == "IBGE / SIDRA 7060"
    comparisons = group_comparisons(
        group_rows, ["7170"], "2020-01", "2020-03", "2020-04", "2020-06"
    )
    comp = group_comparison_csv_bytes(comparisons)
    records = list(csv.DictReader(io.StringIO(comp.decode("utf-8-sig")), delimiter=";"))
    assert len(records) == 4 and records[3]["Diferenca A menos B (p.p.)"] == ""


def test_group_csv_rejects_forged_text_and_missing_outside_known_window(group_rows):
    row = dict(next(r for r in group_rows if r["period"] == "2024-01"))
    for field, value in [("group_name", "=1"), ("retrieved_at", "=1"), ("twelve_month", None)]:
        with pytest.raises(ValidationError):
            group_csv_bytes([{**row, field: value}])


def test_cli_demo_and_group_export(tmp_path, capsys):
    from radar_inflacao.cli import main

    options = ["--data-dir", str(tmp_path / "db")]
    assert main([*options, "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["groups"]["rows"] == 738
    target = tmp_path / "groups.csv"
    args = [
        *options,
        "export",
        "--dataset",
        "groups",
        "--groups",
        "7170",
        "7625",
        "--from",
        "2024-01",
        "--to",
        "2024-03",
        "--output",
        str(target),
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["exported"] == 6
    assert main(args) == 2 and "já existe" in capsys.readouterr().out


def test_group_client_refuses_other_origins():
    with pytest.raises(SourceError):
        GroupSource().fetch("https://servicodados.ibge.gov.br/api/v3/agregados/1737/metadados")


def test_upgrade_schema_1_keeps_original_observations(tmp_path):
    # Banco mínimo com as tabelas e tipos exatos da versão 0.2.1.
    directory = tmp_path / "legacy"
    directory.mkdir()
    with duckdb.connect(str(directory / "radar.duckdb")) as db:
        db.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO schema_version VALUES(1)")
        db.execute("""CREATE TABLE ingestion(
            id VARCHAR PRIMARY KEY,started_at TIMESTAMPTZ,finished_at TIMESTAMPTZ,
            mode VARCHAR,retrieved_at VARCHAR,source_url VARCHAR,raw_sha256 VARCHAR,
            metadata_sha256 VARCHAR,raw_file VARCHAR,start_month VARCHAR,end_month VARCHAR,
            status VARCHAR,inserted INTEGER DEFAULT 0,updated INTEGER DEFAULT 0,
            unchanged INTEGER DEFAULT 0,error VARCHAR DEFAULT '')""")
        db.execute("""CREATE TABLE observation(period DATE PRIMARY KEY,
            monthly DECIMAL(14,6) NOT NULL,year_to_date DECIMAL(14,6) NOT NULL,
            twelve_month DECIMAL(14,6) NOT NULL,
            run_id VARCHAR NOT NULL REFERENCES ingestion(id))""")
        db.execute("INSERT INTO ingestion(id,status) VALUES('old','SUCCESS')")
        db.execute("INSERT INTO observation VALUES('2024-01-01',0.42,0.42,4.51,'old')")
    repo = Repository(directory)
    snapshot = repo.snapshot(include_groups=True)
    assert snapshot["rows"][0]["monthly"] == Decimal("0.42")
    assert snapshot["groups"] == []
    with repo.locked() as db:
        assert db.execute("SELECT version FROM schema_version").fetchone() == (4,)


def test_group_snapshot_is_stable_during_process_lock(group_rows, repository):
    before = group_csv_bytes(group_rows)
    script = """
from pathlib import Path
from radar_inflacao.storage import Repository
import sys
with Repository(Path(sys.argv[1])).locked() as db:
    db.execute('BEGIN TRANSACTION')
    db.execute("UPDATE group_observation SET monthly=9.99 WHERE group_id='7170'")
    print('LOCKED',flush=True)
    sys.stdin.readline()
    db.execute('COMMIT')
"""
    with subprocess.Popen(
        [sys.executable, "-c", script, str(repository.directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout.readline().strip() == "LOCKED"
            with pytest.raises(BusyError):
                repository.snapshot(include_groups=True)
            assert group_csv_bytes(group_rows) == before
        finally:
            _, error = process.communicate("\n", timeout=15)
        assert process.returncode == 0, error
    assert group_csv_bytes(repository.snapshot(include_groups=True)["groups"]) != before


def test_group_view_offline_filters_comparison_and_empty_selection(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="view").set_value("Grupos de despesas").run()
    assert not app.exception
    app.selectbox(key="g_start").select("2024-01")
    app.selectbox(key="g_end").select("2024-03")
    app.selectbox(key="g_mode").select("year").run()
    assert not app.exception
    assert len(app.get("download_button")) == 3
    assert all(b.proto.ignore_rerun for b in app.get("download_button"))
    assert any("B 2023-01 a 2023-03" in c.value for c in app.caption)
    ranking = next(d.value for d in app.dataframe if "Posição" in d.value.columns)
    assert len(ranking) == 3
    app.multiselect(key="g_codes").set_value([]).run()
    assert any("pelo menos um grupo" in i.value for i in app.info)


def test_group_view_missing_12_and_unavailable_reference(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="view").set_value("Grupos de despesas").run()
    app.selectbox(key="g_start").select("2020-01")
    app.selectbox(key="g_end").select("2020-03")
    app.selectbox(key="g_measure").select("twelve_month").run()
    assert not app.exception
    assert any("indicador não está disponível" in i.value for i in app.info)
    assert any("Comparação dos grupos indisponível" in i.value for i in app.info)


def test_group_comparison_export_rejects_forged_count(group_rows):
    from dataclasses import replace

    comparisons = group_comparisons(
        group_rows, ["7170"], "2024-01", "2024-03", "2023-01", "2023-03"
    )
    c = comparisons["7170"]
    with pytest.raises(ValidationError):
        group_comparison_csv_bytes({"7170": replace(c, a=replace(c.a, count="=1"))})


def test_cli_reports_partial_update_without_claiming_all_success(tmp_path, monkeypatch, capsys):
    from radar_inflacao.cli import main
    from radar_inflacao.pipeline import Pipeline

    monkeypatch.setattr(Pipeline, "update", lambda *args, **kwargs: {"status": "SUCCESS"})

    def fail(*args, **kwargs):
        raise SourceError("Grupo indisponível")

    monkeypatch.setattr(GroupPipeline, "update", fail)
    assert main(["--data-dir", str(tmp_path), "update"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PARTIAL" and "national" in result["completed"]
    assert "groups" in result["errors"]


def test_ranking_chart_keeps_numeric_order_after_selection_changes():
    from radar_inflacao.group_view import ranking_chart

    rows = [
        {"group_id": "7660", "monthly": Decimal("0.83")},
        {"group_id": "7445", "monthly": Decimal("0.25")},
        {"group_id": "7625", "monthly": Decimal("-0.65")},
    ]
    spec = ranking_chart(rows).to_dict()
    assert spec["encoding"]["y"]["sort"] == [
        "Saúde e cuidados pessoais",
        "Habitação",
        "Transportes",
    ]
