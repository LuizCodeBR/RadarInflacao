"""INPC e comparador nacional: contratos, precisão, publicação e interface."""

import copy
import csv
import hashlib
import io
import json
import shutil
from dataclasses import replace
from decimal import Decimal, Inexact, Rounded, localcontext

import httpx
import pytest
from conftest import ROOT

from radar_inflacao import index_storage
from radar_inflacao.cli import main
from radar_inflacao.errors import BusyError, RadarError, SourceError, ValidationError
from radar_inflacao.index_report import index_comparison_csv_bytes, index_csv_bytes
from radar_inflacao.indices import index_comparisons, index_pairs
from radar_inflacao.inpc import (
    InpcPipeline,
    InpcSource,
    inpc_data_url,
    parse_inpc_observations,
    validate_inpc_metadata,
)
from radar_inflacao.model import periods
from radar_inflacao.pipeline import Pipeline
from radar_inflacao.quality import build_quality
from radar_inflacao.quality_report import changes_csv_bytes, quality_csv_bytes
from radar_inflacao.source import Download
from radar_inflacao.storage import Repository

SAMPLE = ROOT / "sample/inpc"


@pytest.fixture(scope="module")
def index_template(tmp_path_factory):
    directory = tmp_path_factory.mktemp("index-seed") / "data"
    repo = Repository(directory)
    Pipeline(repo, ROOT / "sample").demo()
    InpcPipeline(repo, SAMPLE).demo()
    return directory


@pytest.fixture
def index_repository(index_template, tmp_path):
    target = tmp_path / "data"
    shutil.copytree(index_template, target)
    return Repository(target)


@pytest.fixture
def indices(index_repository):
    return index_repository.snapshot(include_indices=True)["indices"]


def records(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))


class FakeInpc:
    def __init__(self, changed=False, fail=False):
        self.changed, self.fail, self.requested = changed, fail, None

    def metadata(self):
        return Download((SAMPLE / "metadata-1736.json").read_bytes(), "metadata")

    def observations(self, start, end):
        self.requested = (start, end)
        if self.fail:
            raise SourceError("Falha simulada do INPC")
        payload = json.loads((SAMPLE / "ibge-1736.json").read_bytes())
        for variable in payload:
            source = variable["resultados"][0]["series"][0]["serie"]
            selected = {p.replace("-", ""): source[p.replace("-", "")] for p in periods(start, end)}
            if self.changed and variable["id"] == "44" and "202610" in selected:
                selected["202610"] = "9.99"
            variable["resultados"][0]["series"][0]["serie"] = selected
        return Download(json.dumps(payload, ensure_ascii=False).encode(), inpc_data_url(start, end))


def test_sample_identity_counts_and_official_last_values():
    manifest = json.loads((SAMPLE / "manifest.json").read_bytes())
    raw = (SAMPLE / "ibge-1736.json").read_bytes()
    meta = (SAMPLE / "metadata-1736.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    assert hashlib.sha256(meta).hexdigest() == manifest["metadata_sha256"]
    assert validate_inpc_metadata(meta) == "2026-10"
    parsed = parse_inpc_observations(raw, periods("2020-01", "2026-10"))
    assert len(parsed) == 82
    assert (parsed[-1].monthly, parsed[-1].year_to_date, parsed[-1].twelve_month) == (
        Decimal("0.22"),
        Decimal("4.24"),
        Decimal("4.49"),
    )
    assert all(r.twelve_month is not None for r in parsed)


@pytest.mark.parametrize(
    "change",
    [
        "ipca_ids",
        "duplicate",
        "unit",
        "classification",
        "level",
        "location",
        "missing_month",
        "extra_month",
        "missing",
        "null",
        "nan",
        "unicode",
        "negative",
        "oversized",
    ],
)
def test_inpc_response_contract_refuses_invalid_input(change):
    payload = json.loads((SAMPLE / "ibge-1736.json").read_bytes())
    series = payload[0]["resultados"][0]["series"][0]
    if change == "ipca_ids":
        payload[0]["id"] = "63"
    elif change == "duplicate":
        payload[1] = copy.deepcopy(payload[0])
    elif change == "unit":
        payload[0]["unidade"] = "R$"
    elif change == "classification":
        payload[0]["resultados"][0]["classificacoes"] = [{"id": "315"}]
    elif change == "level":
        series["localidade"]["nivel"]["id"] = "N6"
    elif change == "location":
        series["localidade"]["id"] = "2"
    elif change == "missing_month":
        series["serie"].pop("202001")
    elif change == "extra_month":
        series["serie"]["201912"] = "0.10"
    elif change == "missing":
        payload.pop()
    else:
        series["serie"]["202001"] = {
            "null": "...",
            "nan": "NaN",
            "unicode": "０.１２",
            "negative": "-100.01",
            "oversized": "9999999",
        }[change]
    with pytest.raises(ValidationError):
        parse_inpc_observations(json.dumps(payload).encode(), periods("2020-01", "2026-10"))


@pytest.mark.parametrize(
    "change", ["table", "frequency", "territory", "unit", "missing", "duplicate"]
)
def test_inpc_metadata_is_separate_and_strict(change):
    data = json.loads((SAMPLE / "metadata-1736.json").read_bytes())
    if change == "table":
        data["id"] = 1737
    elif change == "frequency":
        data["periodicidade"]["frequencia"] = "anual"
    elif change == "territory":
        data["nivelTerritorial"]["Administrativo"] = ["N1", "N6"]
    elif change == "unit":
        next(v for v in data["variaveis"] if v["id"] == 44)["unidade"] = "R$"
    elif change == "missing":
        data["variaveis"] = [v for v in data["variaveis"] if v["id"] != 44]
    else:
        data["variaveis"].append(copy.deepcopy(data["variaveis"][0]))
    with pytest.raises(ValidationError):
        validate_inpc_metadata(json.dumps(data).encode())


def test_source_uses_correct_url_and_protection():
    calls = []
    raw = FakeInpc().observations("2024-01", "2024-03").raw

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=raw)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = InpcSource(client).observations("2024-01", "2024-03")
    from urllib.parse import unquote

    assert unquote(str(calls[0].url)) == inpc_data_url("2024-01", "2024-03")
    assert len(parse_inpc_observations(result.raw, periods("2024-01", "2024-03"))) == 3
    with pytest.raises(SourceError):
        InpcSource().fetch("https://example.org/")


def test_repeat_incremental_change_history_and_quality(index_repository):
    repo = index_repository
    before = repo.quality_snapshot(dataset="inpc", kind="all")
    assert before["total_changes"] == 246
    assert InpcPipeline(repo, SAMPLE).demo()["change_fields"] == 0
    source = FakeInpc(changed=True)
    result = InpcPipeline(repo, SAMPLE, source).update()
    assert source.requested == ("2024-11", "2026-10")
    assert result["rows"] == 24 and result["updated"] == result["change_fields"] == 1
    changes = repo.quality_snapshot(dataset="inpc", kind="CHANGED")
    row = changes["changes"][0]
    assert (row["old_value"], row["new_value"]) == (Decimal("0.22"), Decimal("9.99"))
    assert len(records(changes_csv_bytes(changes))) == 1
    assert InpcPipeline(repo, SAMPLE, source).update()["change_fields"] == 0
    with pytest.raises(ValidationError):
        InpcPipeline(repo, SAMPLE).demo()
    report = build_quality(repo.quality_snapshot())
    assert report["datasets"][3]["grade"] == "OK"
    assert len(records(quality_csv_bytes(report))) == 16


@pytest.mark.parametrize("stage", ["download", "publication"])
def test_failed_update_preserves_values_and_events(index_repository, monkeypatch, stage):
    before = index_repository.quality_snapshot(dataset="inpc", kind="all")
    worker = InpcPipeline(
        index_repository, SAMPLE, FakeInpc(changed=True, fail=stage == "download")
    )
    if stage == "publication":
        original = worker.publish

        def fail(db, rows, run_id):
            original(db, rows, run_id)
            raise RuntimeError("before commit")

        monkeypatch.setattr(worker, "publish", fail)
    with pytest.raises(RadarError):
        worker.update()
    after = index_repository.quality_snapshot(dataset="inpc", kind="all")
    assert after["changes"] == before["changes"]
    assert after["datasets"][3]["rows"] == before["datasets"][3]["rows"]
    assert after["datasets"][3]["latest_attempt"]["status"] == "FAILED"


def test_pairs_exact_sign_and_distinct_source_ids(indices):
    pair = index_pairs(indices, "2026-10", "2026-10")[0]
    assert pair["differences"] == {
        "monthly": Decimal("0.08"),
        "year_to_date": Decimal("0.14"),
        "twelve_month": Decimal("-0.14"),
    }
    assert pair["ipca"]["run_id"] != pair["inpc"]["run_id"]
    data = index_csv_bytes(indices, "2026-10", "2026-10")
    row = records(data)[0]
    assert row["INPC menos IPCA Variação mensal (p.p.)"] == "0,08"
    assert row["Fonte IPCA"] == "IBGE / SIDRA 1737"
    assert row["Fonte INPC"] == "IBGE / SIDRA 1736"
    assert data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data
    assert None not in row


@pytest.mark.parametrize(
    "kind", ["missing_inpc", "missing_ipca", "duplicate", "reversed", "unknown"]
)
def test_coverage_never_truncates_or_fills_zero(indices, kind):
    if kind == "missing_inpc":
        indices["inpc"] = [r for r in indices["inpc"] if r["period"] != "2024-02"]
    elif kind == "missing_ipca":
        indices["ipca"] = [r for r in indices["ipca"] if r["period"] != "2024-02"]
    elif kind == "duplicate":
        indices["inpc"].append(copy.deepcopy(indices["inpc"][0]))
    elif kind == "unknown":
        indices["other"] = []
    with pytest.raises(ValidationError):
        index_csv_bytes(
            indices,
            "2024-03" if kind == "reversed" else "2024-01",
            "2024-01" if kind == "reversed" else "2024-03",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("monthly", Decimal("NaN")),
        ("twelve_month", None),
        ("mode", "=1"),
        ("raw_sha256", "@SUM(1)"),
        ("run_id", "=HYPERLINK(1)"),
        ("retrieved_at", "2024-01-01"),
        ("run_status", "FAILED"),
        ("period_day", 2),
        ("run_finished_at", None),
        ("source_url", "https://example.org/"),
        ("run_start", "2024-02"),
    ],
)
def test_corrupt_origin_or_value_in_b_is_refused(indices, field, value):
    next(r for r in indices["inpc"] if r["period"] == "2023-01")[field] = value
    with pytest.raises(ValidationError):
        index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")


def test_comparisons_decimal_context_and_csv_equations(indices):
    expected = index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")
    raw = index_comparison_csv_bytes(expected)
    data = records(raw)
    assert len(data) == 4 and all(None not in r for r in data)
    for row in data:

        def value(key, record=row):
            return Decimal(record[key].replace(",", "."))

        assert value("INPC A (%)") - value("IPCA A (%)") == value("INPC menos IPCA em A (p.p.)")
        assert value("IPCA A (%)") - value("IPCA B (%)") == value("IPCA A menos B (p.p.)")
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 2, 1, -1
        context.traps[Inexact] = context.traps[Rounded] = True
        assert index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03") == expected
        assert index_comparison_csv_bytes(expected) == raw
        assert not context.flags[Inexact] and not context.flags[Rounded]


@pytest.mark.parametrize("change", ["windows", "label", "difference", "missing", "none"])
def test_comparison_export_refuses_forged_objects(indices, change):
    comparisons = index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")
    c = comparisons["inpc"]
    if change == "windows":
        comparisons["inpc"] = index_comparisons(
            indices, "2024-02", "2024-03", "2023-02", "2023-03"
        )["inpc"]
    elif change == "missing":
        comparisons.pop("ipca")
    elif change == "none":
        comparisons["inpc"] = replace(c, a=replace(c.a, twelve_month=None))
    else:
        measure = replace(
            c.measures[0],
            **({"label": "=1"} if change == "label" else {"difference": Decimal("100")}),
        )
        comparisons["inpc"] = replace(c, measures=(measure, *c.measures[1:]))
    with pytest.raises(ValidationError):
        index_comparison_csv_bytes(comparisons)


def test_charts_preserve_values_and_altair_global_config(indices):
    import altair as alt

    from radar_inflacao.index_view import difference_chart, evolution_chart

    pairs = index_pairs(indices, "2026-09", "2026-10")
    before = (alt.data_transformers.active, dict(alt.data_transformers.options))
    line = evolution_chart(pairs, "monthly").to_dict()
    gap = difference_chart(pairs, "monthly").to_dict()
    assert gap["encoding"]["y"]["field"] == r"INPC − IPCA (p\.p\.)"
    assert gap["encoding"]["tooltip"][1]["field"] == gap["encoding"]["y"]["field"]
    assert len(line["data"]["values"]) == 4
    assert gap["data"]["values"][-1]["INPC − IPCA (p.p.)"] == 0.08
    assert (alt.data_transformers.active, dict(alt.data_transformers.options)) == before


def test_cli_exports_reimport_and_no_overwrite(index_repository, tmp_path, capsys):
    assert main(["--data-dir", str(index_repository.directory), "demo", "--dataset", "inpc"]) == 0
    assert json.loads(capsys.readouterr().out)["unchanged"] == 82
    for dataset in ("inpc", "indices"):
        target = tmp_path / f"{dataset}.csv"
        args = [
            "--data-dir",
            str(index_repository.directory),
            "export",
            "--dataset",
            dataset,
            "--from",
            "2024-01",
            "--to",
            "2024-03",
            "--output",
            str(target),
        ]
        assert main(args) == 0 and len(records(target.read_bytes())) == 3
        original = target.read_bytes()
        assert main(args) == 2 and target.read_bytes() == original
    target = tmp_path / "ab.csv"
    assert (
        main(
            [
                "--data-dir",
                str(index_repository.directory),
                "compare-indices",
                "--from",
                "2024-01",
                "--to",
                "2024-03",
                "--from-b",
                "2023-01",
                "--to-b",
                "2023-03",
                "--output",
                str(target),
            ]
        )
        == 0
    )
    assert len(records(target.read_bytes())) == 4


def test_schema_4_upgrade_preserves_all_existing_tables(tmp_path):
    from radar_inflacao.area_pipeline import AreaPipeline
    from radar_inflacao.pipeline import GroupPipeline

    repo = Repository(tmp_path / "old")
    Pipeline(repo, ROOT / "sample").demo()
    GroupPipeline(repo, ROOT / "sample/groups").demo()
    AreaPipeline(repo, ROOT / "sample/areas").demo()
    before = repo.quality_snapshot(kind="all")
    with repo.locked() as db:
        for table in ("inpc_change", "inpc_observation", "inpc_ingestion"):
            db.execute(f"DROP TABLE {table}")
        db.execute("DELETE FROM audit_baseline WHERE dataset='inpc'")
        db.execute("UPDATE schema_version SET version=4")
    after = repo.quality_snapshot(kind="all")
    assert after["datasets"][:3] == before["datasets"][:3]
    assert after["changes"] == before["changes"]
    assert after["datasets"][3]["rows"] == []
    with repo.locked() as db:
        assert db.execute("SELECT version FROM schema_version").fetchone() == (5,)


def test_failed_inpc_migration_is_atomic(index_repository):
    with index_repository.locked() as db:
        for table in ("inpc_change", "inpc_observation", "inpc_ingestion"):
            db.execute(f"DROP TABLE {table}")
        db.execute("DELETE FROM audit_baseline WHERE dataset='inpc'")
        db.execute("UPDATE schema_version SET version=4")

        class Fail:
            def execute(self, sql, *args):
                if "CREATE TABLE inpc_change" in sql:
                    raise RuntimeError("migration")
                return db.execute(sql, *args)

        with pytest.raises(RuntimeError):
            index_storage.migrate(Fail())
        assert db.execute("SELECT version FROM schema_version").fetchone() == (4,)
        assert not {r[0] for r in db.execute("SHOW TABLES").fetchall()} & {
            "inpc_observation",
            "inpc_ingestion",
            "inpc_change",
        }


def test_ui_filters_measures_and_downloads(index_repository, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(index_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("IPCA × INPC").run()
    assert not app.exception and len(app.metric) == 3
    assert len(app.get("download_button")) == 2
    assert all(b.proto.ignore_rerun for b in app.get("download_button"))
    app.selectbox(key="i_start").set_value("2024-01")
    app.selectbox(key="i_end").set_value("2024-03").run()
    app.selectbox(key="i_measure").set_value("twelve_month").run()
    assert not app.exception
    assert any("A 2024-01 a 2024-03 · B 2023-10 a 2023-12" in x.value for x in app.caption)
    app.selectbox(key="i_mode").set_value("custom").run()
    app.selectbox(key="i_bs").set_value("2024-02").run()
    assert any("durações diferentes" in x.value for x in app.warning)
    assert any("sobrepõem" in x.value for x in app.info)
    app.selectbox(key="i_start").set_value("2024-04").run()
    assert not app.exception and not app.get("download_button")


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM inpc_observation WHERE period='2026-10-01'",
        "UPDATE inpc_ingestion SET retrieved_at='=1'",
    ],
)
def test_ui_refuses_missing_month_or_corrupt_origin(index_repository, monkeypatch, query):
    from streamlit.testing.v1 import AppTest

    with index_repository.locked() as db:
        db.execute(query)
    monkeypatch.setenv("RADAR_DATA_DIR", str(index_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("IPCA × INPC").run()
    assert not app.exception and not app.get("download_button")
    assert app.error
    if query.startswith("DELETE"):
        assert any("coberturas diferentes" in x.value for x in app.warning)


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_real_inpc_process_snapshot_and_reports_stay_consistent(index_repository, finish):
    import subprocess
    import sys

    from test_group_review import _line

    before = index_repository.quality_snapshot(dataset="inpc", kind="all")
    indices = index_repository.snapshot(include_indices=True)["indices"]

    def exports(snapshot):
        return (
            index_csv_bytes(snapshot, "2026-10", "2026-10"),
            index_comparison_csv_bytes(
                index_comparisons(snapshot, "2026-10", "2026-10", "2026-09", "2026-09")
            ),
        )

    prepared = exports(indices)
    script = r"""
import os
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from test_indices import FakeInpc,SAMPLE
from radar_inflacao.inpc import InpcPipeline
from radar_inflacao.storage import Repository
worker=InpcPipeline(Repository(Path(sys.argv[1])),SAMPLE,FakeInpc(changed=True))
original=worker.publish
def pause(db,rows,run_id):
    result=original(db,rows,run_id)
    print('UNCOMMITTED',flush=True)
    if sys.stdin.readline() != 'COMMIT\n':
        os._exit(73)
    return result
worker.publish=pause
print(worker.update()['status'],flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(index_repository.directory), str(ROOT / "tests")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _line(process) == "UNCOMMITTED"
        with pytest.raises(BusyError):
            index_repository.snapshot(include_indices=True)
        assert exports(indices) == prepared
        if finish == "commit":
            out, err = process.communicate("COMMIT\n", timeout=30)
            assert process.returncode == 0 and "SUCCESS" in out, err
        else:
            process.communicate("CRASH\n", timeout=30)
            assert process.returncode == 73
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)
    after = index_repository.quality_snapshot(dataset="inpc", kind="all")
    assert after["datasets"][0]["rows"] == before["datasets"][0]["rows"]
    if finish == "crash":
        assert after["changes"] == before["changes"]
        assert after["datasets"][3]["rows"] == before["datasets"][3]["rows"]
        assert after["datasets"][3]["latest_attempt"]["status"] == "INTERRUPTED"
    else:
        assert after["total_changes"] == before["total_changes"] + 1
        new = index_repository.snapshot(include_indices=True)["indices"]
        assert index_pairs(new, "2026-10", "2026-10")[0]["differences"]["monthly"] == Decimal(
            "9.85"
        )
    assert exports(indices) == prepared


def test_missing_b_does_not_remove_valid_period_export(indices):
    indices["inpc"] = [r for r in indices["inpc"] if r["period"] != "2023-02"]
    assert len(records(index_csv_bytes(indices, "2024-01", "2024-03"))) == 3
    with pytest.raises(ValidationError, match="INPC"):
        index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")


def test_cross_table_identity_cannot_be_swapped(indices):
    indices["ipca"], indices["inpc"] = indices["inpc"], indices["ipca"]
    with pytest.raises(ValidationError, match="Origem incompatível"):
        index_csv_bytes(indices, "2024-01", "2024-03")


def test_zero_and_negative_differences_remain_numeric(indices):
    for key in indices:
        for r in indices[key]:
            r["monthly"] = Decimal("-0.123456")
    data = records(index_csv_bytes(indices, "2024-01", "2024-01"))[0]
    assert data["INPC Variação mensal (%)"] == "-0,123456"
    assert data["INPC menos IPCA Variação mensal (p.p.)"] == "0"


def test_ui_rounds_estimates_but_csv_preserves_calculation(indices):
    from radar_inflacao.index_report import comparison_records

    result = index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")
    display = comparison_records(result, display=True)
    exact = records(index_comparison_csv_bytes(result))
    assert display[0]["IPCA A (%)"] == "1,42%"
    assert exact[0]["IPCA A (%)"] == "1,4154915776"


def test_available_early_period_keeps_official_twelve_month(indices):
    result = index_comparisons(indices, "2020-01", "2020-03", "2020-01", "2020-01")
    assert len(records(index_comparison_csv_bytes(result))) == 4
    assert result["inpc"].a.twelve_month is not None
    assert result["inpc"].overlap and not result["inpc"].same_length
