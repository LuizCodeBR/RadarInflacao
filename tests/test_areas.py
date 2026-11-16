"""Áreas: fonte, contratos, exatidão, persistência, CSV e painel offline."""

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

from radar_inflacao import area_storage
from radar_inflacao.area_pipeline import AreaPipeline
from radar_inflacao.area_report import area_comparison_csv_bytes, area_csv_bytes
from radar_inflacao.area_source import AreaSource
from radar_inflacao.areas import (
    AREAS,
    LOCATIONS,
    area_comparisons,
    area_data_url,
    area_ranking,
    bundle_bytes,
    difference,
    filter_area_rows,
    parse_area_bundle,
    parse_area_response,
    validate_area_metadata,
    windows,
)
from radar_inflacao.cli import main
from radar_inflacao.errors import BusyError, RadarError, SourceError, ValidationError
from radar_inflacao.model import periods
from radar_inflacao.quality import build_quality
from radar_inflacao.quality_report import changes_csv_bytes
from radar_inflacao.source import Download
from radar_inflacao.storage import Repository

SAMPLE = ROOT / "sample/areas"


@pytest.fixture(scope="module")
def area_template(tmp_path_factory):
    directory = tmp_path_factory.mktemp("area-seed") / "data"
    AreaPipeline(Repository(directory), SAMPLE).demo()
    return directory


@pytest.fixture
def area_repository(area_template, tmp_path):
    target = tmp_path / "data"
    shutil.copytree(area_template, target)
    return Repository(target)


@pytest.fixture
def rows(area_repository):
    return area_repository.snapshot(include_areas=True)["areas"]


def part_payload():
    bundle = json.loads((SAMPLE / "ibge-7060.json").read_bytes())
    return json.loads(bundle["parts"][0]["body"])


class FakeSource:
    def __init__(self, changed=False, fail=False):
        self.changed = changed
        self.fail = fail
        self.requested = None

    def metadata(self):
        return Download((SAMPLE / "metadata-7060.json").read_bytes(), "metadata")

    def observations(self, start, end):
        if self.fail:
            raise SourceError("Falha regional simulada")
        self.requested = (start, end)
        bundle = json.loads((SAMPLE / "ibge-7060.json").read_bytes())
        maps = {}
        for part in bundle["parts"]:
            for variable in json.loads(part["body"]):
                for serie in variable["resultados"][0]["series"]:
                    loc = serie["localidade"]
                    key = loc["nivel"]["id"] + ":" + loc["id"]
                    entry = maps.setdefault((variable["id"], key), {"localidade": loc, "serie": {}})
                    entry["serie"].update(serie["serie"])
        parts = []
        for begin, finish in windows(start, end):
            variables = []
            for identifier in ("63", "69", "2265"):
                series = []
                for key in LOCATIONS:
                    entry = maps[(identifier, key)]
                    values = {
                        p.replace("-", ""): entry["serie"][p.replace("-", "")]
                        for p in periods(begin, finish)
                    }
                    if (
                        self.changed
                        and identifier == "63"
                        and key == "N7:3501"
                        and "202610" in values
                    ):
                        values["202610"] = "9.99"
                    series.append({"localidade": entry["localidade"], "serie": values})
                variables.append(
                    {
                        "id": identifier,
                        "unidade": "" if identifier == "2265" and begin < "2020-12" else "%",
                        "resultados": [
                            {
                                "classificacoes": [
                                    {"id": "315", "categoria": {"7169": "Índice geral"}}
                                ],
                                "series": series,
                            }
                        ],
                    }
                )
            parts.append(
                Download(
                    json.dumps(variables, ensure_ascii=False).encode(), area_data_url(begin, finish)
                )
            )
        return Download(bundle_bytes(parts), area_data_url(start, end))


def records(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def test_official_sample_contract_and_origin():
    raw = (SAMPLE / "ibge-7060.json").read_bytes()
    manifest = json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    parsed = parse_area_bundle(raw, periods("2020-01", "2026-10"))
    assert len(parsed) == 1394 and sum(r.twelve_month is None for r in parsed) == 187
    assert len(json.loads(raw)["parts"]) == 4
    assert validate_area_metadata((SAMPLE / "metadata-7060.json").read_bytes()) == "2026-10"


@pytest.mark.parametrize(
    "change",
    [
        "missing_area",
        "duplicate_area",
        "wrong_id",
        "wrong_level",
        "wrong_name",
        "missing_month",
        "missing_variable",
        "unit",
        "category",
        "null",
        "nonfinite",
        "extra",
    ],
)
def test_bad_response_is_refused(change):
    payload = part_payload()
    series = payload[0]["resultados"][0]["series"]
    if change == "missing_area":
        series.pop()
    elif change == "duplicate_area":
        series[-1] = series[0]
    elif change == "wrong_id":
        series[-1]["localidade"]["id"] = "999"
    elif change == "wrong_level":
        series[-1]["localidade"]["nivel"]["id"] = "N7"
    elif change == "wrong_name":
        series[-1]["localidade"]["nome"] = "Outra cidade"
    elif change == "missing_month":
        series[-1]["serie"].pop("202001")
    elif change == "missing_variable":
        payload.pop()
    elif change == "unit":
        payload[0]["unidade"] = "R$"
    elif change == "category":
        payload[0]["resultados"][0]["classificacoes"][0]["categoria"] = {"7170": "Alimentação"}
    elif change == "null":
        series[-1]["serie"]["202001"] = "..."
    elif change == "nonfinite":
        series[-1]["serie"]["202001"] = "NaN"
    else:
        series.append(series[0])
    with pytest.raises(ValidationError):
        parse_area_response(json.dumps(payload).encode(), periods("2020-01", "2021-12"))


@pytest.mark.parametrize("change", ["url", "hash", "missing_part", "duplicate_part", "body"])
def test_bad_bundle_refused(change):
    bundle = json.loads((SAMPLE / "ibge-7060.json").read_bytes())
    if change == "url":
        bundle["parts"][0]["url"] = "https://example.org/"
    elif change == "hash":
        bundle["parts"][0]["sha256"] = "a" * 64
    elif change == "missing_part":
        bundle["parts"].pop()
    elif change == "duplicate_part":
        bundle["parts"][1] = bundle["parts"][0]
    else:
        bundle["parts"][0]["body"] = "{}"
    with pytest.raises(ValidationError):
        parse_area_bundle(json.dumps(bundle).encode(), periods("2020-01", "2026-10"))


def test_source_uses_bounded_requests_and_fixed_origin():
    fake = FakeSource()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        # A ordem e os períodos são conhecidos; a URL é comparada abaixo.
        start, end = windows("2020-01", "2026-10")[len(calls) - 1]
        raw = json.loads(fake.observations(start, end).raw)["parts"][0]["body"].encode()
        return httpx.Response(200, content=raw)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = AreaSource(client).observations("2020-01", "2026-10")
        assert len(parse_area_bundle(result.raw, periods("2020-01", "2026-10"))) == 1394
    from urllib.parse import unquote

    assert [unquote(url) for url in calls] == [
        area_data_url(start, end) for start, end in windows("2020-01", "2026-10")
    ]
    assert len(calls) == 4
    with pytest.raises(SourceError):
        AreaSource().fetch("https://example.org/")


def test_source_failure_never_returns_partial_bundle():
    calls = []
    fake = FakeSource()

    def handler(request):
        calls.append(request)
        if len(calls) > 1:
            return httpx.Response(404)
        body = json.loads(fake.observations("2020-01", "2021-12").raw)["parts"][0]["body"].encode()
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(SourceError):
        AreaSource(client).observations("2020-01", "2026-10")
    assert len(calls) == 2


def test_import_repeat_update_and_history(area_repository):
    worker = AreaPipeline(area_repository, SAMPLE)
    before = area_repository.quality_snapshot(dataset="areas", kind="all")
    assert before["total_changes"] == 4182
    result = worker.demo()
    assert result["unchanged"] == 1394 and result["change_fields"] == 0
    source = FakeSource(changed=True)
    changed = AreaPipeline(area_repository, SAMPLE, source).update()
    assert source.requested == ("2024-11", "2026-10")
    assert changed["rows"] == 408 and changed["updated"] == changed["change_fields"] == 1
    snapshot = area_repository.quality_snapshot(dataset="areas", area_key="N7:3501")
    assert snapshot["total_changes"] == 1
    assert snapshot["changes"][0]["new_value"] == Decimal("9.99")
    assert snapshot["changes"][0]["old_value"] == Decimal("0.22")
    assert "São Paulo" in changes_csv_bytes(snapshot).decode("utf-8-sig")
    assert AreaPipeline(area_repository, SAMPLE, source).update()["change_fields"] == 0
    with pytest.raises(ValidationError):
        worker.demo()


def test_failed_publication_rolls_back_both_values_and_history(area_repository, monkeypatch):
    before = area_repository.quality_snapshot(kind="all")
    original = area_storage.upsert

    def fail(db, observations, run_id):
        original(db, observations[-17:], run_id)
        raise RuntimeError("before commit")

    monkeypatch.setattr(area_storage, "upsert", fail)
    with pytest.raises(RadarError):
        AreaPipeline(area_repository, SAMPLE, FakeSource(changed=True)).update()
    after = area_repository.quality_snapshot(kind="all")
    assert after["changes"] == before["changes"]
    assert after["datasets"][2]["rows"] == before["datasets"][2]["rows"]
    assert after["datasets"][2]["latest_attempt"]["status"] == "FAILED"


def test_ranking_difference_exact_and_separate_from_price_levels(rows):
    ranking = area_ranking(rows, list(AREAS), "2026-10")
    assert len(ranking) == 16
    assert ranking[0]["area_key"] == "N7:1501"
    assert ranking[-1]["area_key"] == "N7:4101"
    assert ranking[0]["differences"]["monthly"] == Decimal("0.56")
    assert ranking[-1]["differences"]["monthly"] == Decimal("-0.81")
    assert ranking[0]["brazil"]["monthly"] == Decimal("0.14")
    assert all(r["area_key"] != "N1:1" for r in ranking)


def test_ranking_ties_and_decimal_traps(rows):
    selected = filter_area_rows(rows, ["N1:1", *AREAS], "2026-10", "2026-10", brazil=True)
    for row in selected:
        row["monthly"] = Decimal("0.123456")
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        ranked = area_ranking(selected, list(AREAS), "2026-10")
        assert [r["area_key"] for r in ranked] == list(AREAS)
        assert all(r["differences"]["monthly"] == 0 for r in ranked)


@pytest.mark.parametrize(
    "keys", [[], ["N1:1"], ["N7:9999"], ["N7:3501", "N7:3501"], None, ["N6:3501"]]
)
def test_invalid_area_selection(rows, keys):
    with pytest.raises(ValidationError):
        filter_area_rows(rows, keys, "2024-01", "2024-03")


def test_csv_values_brazil_and_both_origins(rows):
    data = area_csv_bytes(rows, ["N7:4101"], "2026-10", "2026-10")
    item = records(data)[0]
    assert item["Mensal (%)"] == "-0,67"
    assert item["Brasil mensal (%)"] == "0,14"
    assert item["Diferenca mensal (p.p.)"] == "-0,81"
    assert item["Nivel territorial"] == "N7"
    assert item["Coleta ID"] == item["Brasil Coleta ID"]
    early = records(area_csv_bytes(rows, ["N7:3501"], "2020-01", "2020-01"))[0]
    assert (
        early["12 meses (%)"]
        == early["Brasil 12 meses (%)"]
        == early["Diferenca 12 meses (p.p.)"]
        == ""
    )
    assert data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_sha256", "=1"),
        ("run_id", "=1"),
        ("retrieved_at", "\t=1"),
        ("monthly", Decimal("NaN")),
        ("area_name", "=SUM(1)"),
        ("area_key", "=1"),
    ],
)
def test_csv_hostile_or_corrupt_fields_refused(rows, field, value):
    target = next(r for r in rows if r["area_key"] == "N7:3501" and r["period"] == "2024-01")
    target[field] = value
    with pytest.raises(ValidationError):
        area_csv_bytes(rows, ["N7:3501"], "2024-01", "2024-01")


def test_csv_missing_reference_or_coverage_never_exports_zero(rows):
    rows = [r for r in rows if not (r["area_key"] == "N1:1" and r["period"] == "2024-01")]
    with pytest.raises(ValidationError):
        area_csv_bytes(rows, ["N7:3501"], "2024-01", "2024-03")


def test_period_comparisons_csv_context_and_absence(rows):
    comparison = area_comparisons(rows, ["N7:3501"], "2024-01", "2024-03", "2023-01", "2023-03")
    before = area_comparison_csv_bytes(comparison)
    assert len(records(before)) == 4
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        assert area_comparison_csv_bytes(comparison) == before
        assert (
            area_comparisons(rows, ["N7:3501"], "2024-01", "2024-03", "2023-01", "2023-03")
            == comparison
        )
    early = area_comparisons(rows, ["N7:3501"], "2020-01", "2020-02", "2020-03", "2020-04")
    assert early["N7:3501"].measures[3].a is None
    assert records(area_comparison_csv_bytes(early))[-1]["Area menos Brasil A (p.p.)"] == ""


def test_inconsistent_comparison_is_refused(rows):
    comparison = area_comparisons(rows, ["N7:3501"], "2024-01", "2024-03", "2023-01", "2023-03")
    value = comparison["N7:3501"]
    comparison["N7:3501"] = replace(
        value, measures=(replace(value.measures[0], label="=1"), *value.measures[1:])
    )
    with pytest.raises(ValidationError):
        area_comparison_csv_bytes(comparison)


def test_difference_does_not_round_large_estimates():
    a = Decimal("123456789012345678901234567890123456789.123456")
    b = Decimal("0.000001")
    assert difference(a, b) == Decimal("123456789012345678901234567890123456789.123455")


def test_quality_area_checks_and_history_filter(area_repository):
    report = build_quality(
        area_repository.quality_snapshot(dataset="areas", kind="ADDED", area_key="N1:1")
    )
    assert report["datasets"][2]["grade"] == "OK"
    assert report["total_changes"] == 246
    assert len(records(changes_csv_bytes(report))) == 246
    with area_repository.locked() as db:
        db.execute("DELETE FROM area_observation WHERE period='2024-01-01' AND area_key='N7:3501'")
    assert build_quality(area_repository.quality_snapshot())["datasets"][2]["grade"] == "ERROR"


@pytest.mark.parametrize(
    "filters",
    [
        {"dataset": "national", "area_key": "N7:3501"},
        {"dataset": "areas", "area_key": "N7:9999"},
        {"dataset": "areas", "group_id": "7170"},
    ],
)
def test_quality_invalid_area_filters(area_repository, filters):
    with pytest.raises(ValidationError):
        area_repository.quality_snapshot(**filters)


def test_cli_area_export_and_no_overwrite(area_repository, tmp_path, capsys):
    output = tmp_path / "areas.csv"
    args = [
        "--data-dir",
        str(area_repository.directory),
        "export",
        "--dataset",
        "areas",
        "--areas",
        "N7:3501",
        "--from",
        "2024-01",
        "--to",
        "2024-03",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert len(records(output.read_bytes())) == 3
    capsys.readouterr()
    assert main(args) == 2 and "já existe" in capsys.readouterr().out


def test_area_view_offline_filters_downloads_and_missing_comparison(area_repository, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(area_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("Comparar áreas").run()
    assert not app.exception
    assert len(app.get("download_button")) == 3
    assert all(b.proto.ignore_rerun for b in app.get("download_button"))
    app.multiselect(key="a_keys").set_value(list(AREAS)).run()
    assert len(next(d.value for d in app.dataframe if "Posição" in d.value)) == 16
    app.selectbox(key="a_start").set_value("2020-01")
    app.selectbox(key="a_end").set_value("2020-03").run()
    assert not app.exception
    assert any("Comparação regional indisponível" in i.value for i in app.info)
    app.selectbox(key="a_measure").set_value("twelve_month").run()
    assert any("Indicador indisponível" in i.value for i in app.info)
    app.multiselect(key="a_keys").set_value([]).run()
    assert not app.exception and not app.get("download_button")


def _remove_regional_schema(db):
    for table in ("area_change", "area_observation", "area_dimension", "area_ingestion"):
        db.execute(f"DROP TABLE {table}")
    db.execute("DELETE FROM audit_baseline WHERE dataset='areas'")
    db.execute("UPDATE schema_version SET version=3")


def test_schema_3_to_4_preserves_existing_values_and_history(tmp_path):
    from radar_inflacao.pipeline import GroupPipeline, Pipeline

    repository = Repository(tmp_path / "legacy")
    Pipeline(repository, ROOT / "sample").demo()
    GroupPipeline(repository, ROOT / "sample/groups").demo()
    before = repository.quality_snapshot(kind="all")
    with repository.locked() as db:
        _remove_regional_schema(db)
    after = repository.quality_snapshot(kind="all")
    assert after["changes"] == before["changes"]
    assert after["datasets"][:2] == before["datasets"][:2]
    assert after["datasets"][2]["rows"] == []
    with repository.locked() as db:
        assert db.execute("SELECT version FROM schema_version").fetchone() == (4,)


def test_failed_regional_migration_is_atomic(area_repository):
    with area_repository.locked() as db:
        _remove_regional_schema(db)

        class Fail:
            def execute(self, sql, *args):
                if "CREATE TABLE area_change" in sql:
                    raise RuntimeError("migration")
                return db.execute(sql, *args)

            def executemany(self, *args):
                return db.executemany(*args)

        with pytest.raises(RuntimeError):
            area_storage.migrate(Fail())
        assert db.execute("SELECT version FROM schema_version").fetchone() == (3,)
        tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
        assert not tables & {"area_ingestion", "area_observation", "area_dimension", "area_change"}
    assert area_repository.snapshot(include_areas=True)["areas"] == []


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_regional_pipeline_snapshot_commit_or_crash(area_repository, finish):
    import subprocess
    import sys

    from test_group_review import _line

    before = area_repository.quality_snapshot(dataset="areas", kind="all")
    rows = before["datasets"][2]["rows"]
    data = area_csv_bytes(rows, ["N7:3501"], "2026-10", "2026-10")
    history = changes_csv_bytes(before)
    script = r"""
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from test_areas import FakeSource,SAMPLE
from radar_inflacao.area_pipeline import AreaPipeline
from radar_inflacao import area_storage
from radar_inflacao.storage import Repository
original=area_storage.upsert
def pause(db,rows,run_id):
    result=original(db,rows,run_id)
    print('UNCOMMITTED',flush=True)
    sys.stdin.readline()
    return result
area_storage.upsert=pause
result=AreaPipeline(Repository(Path(sys.argv[1])),SAMPLE,FakeSource(changed=True)).update()
print(result['status'],flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(area_repository.directory), str(ROOT / "tests")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _line(process) == "UNCOMMITTED"
        with pytest.raises(BusyError):
            area_repository.quality_snapshot()
        assert changes_csv_bytes(before) == history
        assert area_csv_bytes(rows, ["N7:3501"], "2026-10", "2026-10") == data
        if finish == "commit":
            out, err = process.communicate("\n", timeout=30)
            assert process.returncode == 0 and "SUCCESS" in out, err
        else:
            process.kill()
            process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)
    after = area_repository.quality_snapshot(dataset="areas", kind="all")
    if finish == "crash":
        assert after["changes"] == before["changes"]
        assert after["datasets"][2]["rows"] == rows
        assert after["datasets"][2]["latest_attempt"]["status"] == "INTERRUPTED"
    else:
        assert after["total_changes"] == before["total_changes"] + 1
        assert after["datasets"][2]["latest_attempt"]["status"] == "SUCCESS"


@pytest.mark.parametrize("change", ["territory", "category"])
def test_area_metadata_requires_territories_and_general_index(change):
    data = json.loads((SAMPLE / "metadata-7060.json").read_bytes())
    if change == "territory":
        data["nivelTerritorial"]["Administrativo"] = ["N1"]
    else:
        next(c for c in data["classificacoes"][0]["categorias"] if c["id"] == 7169)["nome"] = (
            "Outro"
        )
    with pytest.raises(ValidationError):
        validate_area_metadata(json.dumps(data).encode())


def test_regional_source_download_failure_preserves_publication(area_repository):
    before = area_repository.quality_snapshot(dataset="areas", kind="all")
    with pytest.raises(SourceError):
        AreaPipeline(area_repository, SAMPLE, FakeSource(fail=True)).update()
    after = area_repository.quality_snapshot(dataset="areas", kind="all")
    assert after["changes"] == before["changes"]
    assert after["datasets"][2]["rows"] == before["datasets"][2]["rows"]
    assert after["datasets"][2]["latest_attempt"]["stage"] == "DOWNLOAD"


def test_local_corruption_blocks_regional_charts_and_downloads(area_repository, monkeypatch):
    from streamlit.testing.v1 import AppTest

    with area_repository.locked() as db:
        db.execute("DELETE FROM area_observation WHERE area_key='N7:3501' AND period='2024-01-01'")
    monkeypatch.setenv("RADAR_DATA_DIR", str(area_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("Comparar áreas").run()
    assert not app.exception
    assert any("Dados regionais inválidos" in e.value for e in app.error)
    assert not app.get("download_button")
