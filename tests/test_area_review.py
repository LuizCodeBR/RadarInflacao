"""Revisão separada das áreas: regressões de integridade, origem e concorrência."""

import copy
import json
from decimal import Decimal

import httpx
import pytest
import test_areas as area_fixtures
from test_areas import SAMPLE, FakeSource, records

from radar_inflacao.area_pipeline import AreaPipeline
from radar_inflacao.area_report import area_comparison_csv_bytes, area_csv_bytes
from radar_inflacao.area_source import AreaSource
from radar_inflacao.areas import area_comparisons, area_ranking, validate_area_metadata
from radar_inflacao.errors import SourceError, ValidationError

area_template = area_fixtures.area_template
area_repository = area_fixtures.area_repository
rows = area_fixtures.rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_sha256", "=HYPERLINK(1)"),
        ("retrieved_at", "2024-01-01"),
        ("run_id", "not-a-uuid"),
        ("mode", ["live"]),
    ],
)
def test_comparison_refuses_invalid_origin_in_period_b(rows, field, value):
    row = next(r for r in rows if r["period"] == "2023-01" and r["area_key"] == "N7:3501")
    row[field] = value
    with pytest.raises(ValidationError):
        area_comparison_csv_bytes(
            area_comparisons(rows, ["N7:3501"], "2024-01", "2024-03", "2023-01", "2023-03")
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "00000000-0000-0000-0000-000000000001"),
        ("raw_sha256", "b" * 64),
        ("retrieved_at", "2026-11-16T12:00:00+00:00"),
        ("mode", "live"),
    ],
)
@pytest.mark.parametrize("operation", ["period", "ranking", "comparison"])
def test_area_and_brazil_cannot_mix_collection_versions(rows, field, value, operation):
    target = next(r for r in rows if r["period"] == "2024-01" and r["area_key"] == "N1:1")
    target[field] = value
    with pytest.raises(ValidationError):
        if operation == "period":
            area_csv_bytes(rows, ["N7:3501"], "2024-01", "2024-03")
        elif operation == "ranking":
            area_ranking(rows, ["N7:3501"], "2024-01")
        else:
            area_comparisons(rows, ["N7:3501"], "2024-01", "2024-03", "2023-01", "2023-03")


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE area_ingestion SET status='FAILED'",
        "UPDATE area_ingestion SET finished_at=NULL",
        "UPDATE area_ingestion SET start_month='2024-02'",
        "UPDATE area_ingestion SET source_url='https://example.org/'",
        "UPDATE area_observation SET period='2024-01-02' WHERE period='2024-01-01'",
    ],
)
def test_invalid_stored_publication_cannot_be_exported(area_repository, query):
    with area_repository.locked() as db:
        db.execute(query)
    rows = area_repository.snapshot(include_areas=True)["areas"]
    with pytest.raises(ValidationError):
        area_csv_bytes(rows, ["N7:3501"], "2024-01", "2024-03")


def test_injected_http_client_cannot_follow_redirects_or_disable_timeout():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(302, headers={"Location": "https://example.org/elsewhere"})
        return httpx.Response(200, content=b"[]")

    with (
        httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=True, timeout=None
        ) as client,
        pytest.raises(SourceError),
    ):
        AreaSource(client).metadata()
    assert len(calls) == 1
    assert calls[0].extensions["timeout"]["read"] == 15


def test_regional_metadata_is_independent_of_unrequested_groups():
    payload = json.loads((SAMPLE / "metadata-7060.json").read_bytes())
    payload["variaveis"] = [v for v in payload["variaveis"] if v["id"] != 66]
    category = next(c for c in payload["classificacoes"] if c["id"] == 315)
    category["categorias"] = [c for c in category["categorias"] if c["id"] == 7169]
    payload["classificacoes"].insert(0, {"id": 999, "categorias": []})
    assert validate_area_metadata(json.dumps(payload).encode()) == "2026-10"


@pytest.mark.parametrize(
    "field,value",
    [
        ("monthly", Decimal("sNaN")),
        ("year_to_date", Decimal("Infinity")),
        ("twelve_month", None),
        ("period", "2024-0１"),
        ("area_name", "=HYPERLINK(1)"),
        ("area_key", ["N7:3501"]),
        ("period_day", True),
        ("run_finished_at", "2026-11-16"),
    ],
)
def test_snapshot_rejects_malformed_values_without_decimal_side_effects(rows, field, value):
    from decimal import Inexact, Rounded, localcontext

    from radar_inflacao.areas import filter_area_rows

    row = next(r for r in rows if r["period"] == "2024-01" and r["area_key"] == "N7:3501")
    row[field] = value
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        with pytest.raises(ValidationError):
            filter_area_rows(rows, ["N7:3501"], "2024-01", "2024-03")
        assert not context.flags[Inexact] and not context.flags[Rounded]


@pytest.mark.parametrize(
    "change",
    [
        "variable",
        "unit",
        "duplicate",
        "table",
        "frequency",
        "end",
        "general_index",
        "duplicate_category",
    ],
)
def test_metadata_closed_contract_is_preserved(change):
    data = json.loads((SAMPLE / "metadata-7060.json").read_bytes())
    if change == "variable":
        data["variaveis"] = [v for v in data["variaveis"] if v["id"] != 63]
    elif change == "unit":
        next(v for v in data["variaveis"] if v["id"] == 63)["unidade"] = "R$"
    elif change == "duplicate":
        data["variaveis"].append(copy.deepcopy(data["variaveis"][0]))
    elif change == "table":
        data["id"] = 1737
    elif change == "frequency":
        data["periodicidade"]["frequencia"] = "anual"
    elif change == "end":
        data["periodicidade"]["fim"] = "2026１３"
    else:
        category = next(c for c in data["classificacoes"] if c["id"] == 315)["categorias"]
        general = next(c for c in category if c["id"] == 7169)
        if change == "general_index":
            general["nivel"] = 1
        else:
            category.append(copy.deepcopy(general))
    with pytest.raises(ValidationError):
        validate_area_metadata(json.dumps(data).encode())


def test_incremental_mixed_history_remains_valid(area_repository):
    from radar_inflacao.quality import build_quality

    result = AreaPipeline(area_repository, SAMPLE, FakeSource(changed=True)).update()
    assert result["change_fields"] == 1
    report = build_quality(area_repository.quality_snapshot())
    rows = report["datasets"][2]["rows"]
    assert {r["mode"] for r in rows} == {"sample", "live"}
    assert report["datasets"][2]["grade"] == "OK"
    assert len(records(area_csv_bytes(rows, ["N7:3501"], "2024-01", "2026-10"))) == 34
    assert (
        len(
            records(
                area_comparison_csv_bytes(
                    area_comparisons(rows, ["N7:3501"], "2026-01", "2026-10", "2024-01", "2024-10")
                )
            )
        )
        == 4
    )


def test_quality_reports_cross_collection_corruption(area_repository):
    from radar_inflacao.quality import build_quality

    with area_repository.locked() as db:
        old = db.execute("SELECT id FROM area_ingestion").fetchone()[0]
    AreaPipeline(area_repository, SAMPLE, FakeSource(changed=True)).update()
    with area_repository.locked() as db:
        db.execute(
            "UPDATE area_observation SET run_id=? WHERE area_key='N1:1' AND period='2026-10-01'",
            [old],
        )
    report = build_quality(area_repository.quality_snapshot())
    assert report["datasets"][2]["grade"] == "ERROR"
    check = next(c for c in report["datasets"][2]["checks"] if c["code"] == "provenance")
    assert check["status"] == "ERROR" and "mesma coleta" in check["detail"]


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE area_ingestion SET retrieved_at='=HYPERLINK(1)'",
        "UPDATE area_ingestion SET status='FAILED'",
        "UPDATE area_observation SET period='2024-01-02' WHERE period='2024-01-01'",
    ],
)
def test_ui_refuses_invalid_snapshot_before_all_charts_and_downloads(
    area_repository, monkeypatch, query
):
    from conftest import ROOT
    from streamlit.testing.v1 import AppTest

    with area_repository.locked() as db:
        db.execute(query)
    monkeypatch.setenv("RADAR_DATA_DIR", str(area_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("Comparar áreas").run()
    assert not app.exception
    assert any("Dados regionais inválidos" in e.value for e in app.error)
    assert not app.get("download_button") and not app.get("arrow_vega_lite_chart")


def test_invalid_database_cli_does_not_create_destination(area_repository, tmp_path, capsys):
    from radar_inflacao.cli import main

    with area_repository.locked() as db:
        db.execute("UPDATE area_ingestion SET status='FAILED'")
    target = tmp_path / "blocked.csv"
    assert (
        main(
            [
                "--data-dir",
                str(area_repository.directory),
                "export",
                "--dataset",
                "areas",
                "--output",
                str(target),
            ]
        )
        == 2
    )
    assert not target.exists() and "Publicação regional inválida" in capsys.readouterr().out


def test_chart_limit_and_ranking_values_do_not_change_global_altair_state(rows):
    import altair as alt

    from radar_inflacao.area_view import evolution_chart, ranking_chart
    from radar_inflacao.areas import AREAS, LOCATIONS
    from radar_inflacao.model import periods

    template = [r for r in rows if r["period"] == "2024-01"]
    extended = [
        {**r, "period": period} for period in periods("2020-01", "2119-12") for r in template
    ]
    # Limite sintético do gráfico; não é uma publicação ou previsão do IBGE.
    before = (alt.data_transformers.active, dict(alt.data_transformers.options))
    chart = evolution_chart(extended, "monthly").to_dict()
    assert len(chart["data"]["values"]) == 20400
    assert {r["Área"] for r in chart["data"]["values"]} == set(LOCATIONS.values())
    assert (alt.data_transformers.active, dict(alt.data_transformers.options)) == before
    ranking = ranking_chart(area_ranking(rows, list(AREAS), "2026-10")).to_dict()
    values = ranking["data"]["values"]
    assert len(values) == 16 and all(r["Área"] != "Brasil" for r in values)
    assert values[0]["Diferença para o Brasil (p.p.)"] == 0.56
    assert values[-1]["Variação mensal (%)"] == -0.67
    early = evolution_chart([r for r in rows if r["period"] == "2020-01"], "twelve_month")
    assert all(r["Taxa (%)"] is None for r in early.to_dict()["data"]["values"])


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_brazil_and_area_update_is_atomic_and_all_prepared_exports_stay_stable(
    area_repository, finish
):
    import subprocess
    import sys

    from conftest import ROOT
    from test_group_review import _line

    from radar_inflacao.errors import BusyError
    from radar_inflacao.quality_report import changes_csv_bytes

    def exports(rows):
        return (
            area_csv_bytes(rows, ["N7:3501"], "2026-10", "2026-10"),
            area_csv_bytes(rows, ["N7:3501"], "2026-10", "2026-10", ranking=True),
            area_comparison_csv_bytes(
                area_comparisons(rows, ["N7:3501"], "2026-10", "2026-10", "2026-09", "2026-09")
            ),
        )

    before = area_repository.quality_snapshot(dataset="areas", kind="all")
    rows = before["datasets"][2]["rows"]
    prepared, history = exports(rows), changes_csv_bytes(before)
    script = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from test_areas import FakeSource,SAMPLE
from radar_inflacao.area_pipeline import AreaPipeline
from radar_inflacao.areas import bundle_bytes
from radar_inflacao.source import Download
from radar_inflacao import area_storage
from radar_inflacao.storage import Repository
class Both(FakeSource):
    def observations(self,start,end):
        result=super().observations(start,end)
        parts=[]
        for part in json.loads(result.raw)['parts']:
            data=json.loads(part['body'])
            for var in data:
                for series in var['resultados'][0]['series']:
                    if (var['id']=='63' and series['localidade']['nivel']['id']=='N1'
                        and '202610' in series['serie']):
                        series['serie']['202610']='8.88'
            parts.append(Download(json.dumps(data).encode(),part['url']))
        return Download(bundle_bytes(parts),result.url)
original=area_storage.upsert
def pause(db,rows,run_id):
    result=original(db,rows,run_id)
    print('UNCOMMITTED',flush=True)
    sys.stdin.readline()
    return result
area_storage.upsert=pause
result=AreaPipeline(Repository(Path(sys.argv[1])),SAMPLE,Both(changed=True)).update()
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
            area_repository.snapshot(include_areas=True)
        source = FakeSource(changed=True)
        with pytest.raises(BusyError):
            AreaPipeline(area_repository, SAMPLE, source).update()
        assert source.requested is None
        assert exports(rows) == prepared and changes_csv_bytes(before) == history
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
        assert after["total_changes"] == before["total_changes"] + 2
        result = records(exports(after["datasets"][2]["rows"])[0])[0]
        assert (
            result["Mensal (%)"],
            result["Brasil mensal (%)"],
            result["Diferenca mensal (p.p.)"],
        ) == ("9,99", "8,88", "1,11")
    assert exports(rows) == prepared


def test_two_processes_publish_regional_csv_without_overwrite_or_mixed_bytes(
    area_repository, tmp_path
):
    import subprocess
    import sys

    from test_group_review import _line

    target = tmp_path / "race.csv"
    script = r"""
import sys
from pathlib import Path
from radar_inflacao.storage import Repository
from radar_inflacao.area_report import area_csv_bytes
from radar_inflacao.report import publish_csv
rows=Repository(Path(sys.argv[1])).snapshot(include_areas=True)['areas']
data=area_csv_bytes(rows,[sys.argv[3]],'2024-01','2024-03')
print('READY',flush=True)
sys.stdin.readline()
try:
    publish_csv(Path(sys.argv[2]),data)
    print('PUBLISHED',flush=True)
except FileExistsError:
    print('EXISTS',flush=True)
"""
    processes = []
    try:
        for key in ("N7:3501", "N7:3301"):
            process = subprocess.Popen(
                [sys.executable, "-c", script, str(area_repository.directory), str(target), key],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
            assert _line(process) == "READY"
        for process in processes:
            process.stdin.write("\n")
            process.stdin.flush()
        results = [p.communicate(timeout=30) for p in processes]
        assert sorted(out.strip() for out, err in results) == ["EXISTS", "PUBLISHED"]
        assert all(p.returncode == 0 for p in processes), results
        rows = area_repository.snapshot(include_areas=True)["areas"]
        assert target.read_bytes() in [
            area_csv_bytes(rows, [k], "2024-01", "2024-03") for k in ("N7:3501", "N7:3301")
        ]
        assert not list(tmp_path.glob(".radar-csv-*"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)
