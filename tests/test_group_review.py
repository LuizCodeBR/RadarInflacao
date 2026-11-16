"""Regressões independentes da revisão dos grupos 0.3.1."""

import copy
import csv
import io
from dataclasses import replace
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest
from conftest import ROOT

from radar_inflacao.errors import ValidationError
from radar_inflacao.groups import (
    GROUPS,
    filter_group_rows,
    group_comparisons,
    group_ranking,
    parse_group_observations,
)
from radar_inflacao.model import periods
from radar_inflacao.report import group_comparison_csv_bytes, group_csv_bytes


@pytest.fixture
def reviewed_rows():
    observations = parse_group_observations(
        (ROOT / "sample/groups/ibge-7060.json").read_bytes(), periods("2020-01", "2026-10")
    )
    return [dict(
        period=r.period, group_id=r.group_id, group_name=GROUPS[r.group_id],
        monthly=r.monthly, year_to_date=r.year_to_date, twelve_month=r.twelve_month,
        weight=r.weight, mode="sample", retrieved_at="2026-11-16T12:00:00+00:00",
        raw_sha256="a" * 64, run_id="00000000-0000-0000-0000-000000000001",
    ) for r in observations]


@pytest.mark.parametrize("trapped", [False, True])
def test_ranking_ignores_decimal_context_and_preserves_it(reviewed_rows, trapped):
    rows = filter_group_rows(reviewed_rows, ["7170", "7445"], "2024-01", "2024-01")
    rows[0]["monthly"], rows[1]["monthly"] = Decimal("1.231"), Decimal("1.234")
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = trapped
        context.traps[Rounded] = trapped
        result = group_ranking(rows, ["7170", "7445"], "2024-01")
        assert [r["group_id"] for r in result] == ["7445", "7170"]
        assert context.prec == 3 and context.traps[Inexact] is trapped
        assert not context.flags[Inexact] and not context.flags[Rounded]


@pytest.mark.parametrize("field,value", [
    ("monthly", Decimal("NaN")), ("year_to_date", Decimal("Infinity")),
    ("monthly", Decimal("1E-7")), ("monthly", "=1+1"),
    ("twelve_month", None), ("weight", Decimal("-0.1")),
    ("weight", Decimal("100.1")), ("group_name", "=1+1"),
    ("group_id", ["7170"]), ("period", "2024-0１"),
])
def test_invalid_stored_group_rows_are_refused_before_analysis(reviewed_rows, field, value):
    rows = [dict(r) for r in reviewed_rows if r["period"] == "2024-01"]
    rows[0][field] = value
    with pytest.raises(ValidationError):
        filter_group_rows(rows, list(GROUPS), "2024-01", "2024-01")


def test_group_exports_refuse_duplicates_and_invalid_weight_total(reviewed_rows):
    row = next(r for r in reviewed_rows if r["period"] == "2024-01")
    with pytest.raises(ValidationError):
        group_csv_bytes([row, row])
    rows = [dict(r) for r in reviewed_rows if r["period"] == "2024-01"]
    rows[0]["weight"] = Decimal("99")
    with pytest.raises(ValidationError):
        group_csv_bytes(rows)


@pytest.mark.parametrize("change", [
    "missing_numeric", "missing_12_outside_window", "difference", "empty_measures",
    "duplicate_measure", "wrong_value", "wrong_label", "mixed_periods",
])
def test_comparison_csv_refuses_inconsistent_objects(reviewed_rows, change):
    comparisons = group_comparisons(
        reviewed_rows, ["7170", "7445"], "2024-01", "2024-03", "2023-01", "2023-03"
    )
    c = comparisons["7170"]
    measures = list(c.measures)
    if change == "missing_numeric":
        measures[0] = replace(measures[0], a=None)
    elif change == "missing_12_outside_window":
        c = replace(c, a=replace(c.a, twelve_month=None))
        measures[3] = replace(measures[3], a=None, difference=None)
    elif change == "difference":
        measures[0] = replace(measures[0], difference=Decimal("123"))
    elif change == "empty_measures":
        measures = []
    elif change == "duplicate_measure":
        measures = [measures[0]] * 4
    elif change == "wrong_value":
        measures[0] = replace(measures[0], a=Decimal("123"))
    elif change == "wrong_label":
        measures[0] = replace(measures[0], label="Outro indicador")
    else:
        comparisons["7445"] = group_comparisons(
            reviewed_rows, ["7445"], "2024-02", "2024-03", "2023-02", "2023-03"
        )["7445"]
    comparisons["7170"] = replace(c, measures=tuple(measures))
    with pytest.raises(ValidationError):
        group_comparison_csv_bytes(comparisons)


def test_missing_historical_value_is_blank_only_for_its_measure(reviewed_rows):
    result = group_comparisons(
        reviewed_rows, ["7170"], "2020-01", "2020-03", "2024-01", "2024-03"
    )
    records = list(csv.DictReader(io.StringIO(
        group_comparison_csv_bytes(result).decode("utf-8-sig")
    ), delimiter=";"))
    assert all(r["Valor A (%)"] != "" for r in records[:3])
    assert records[3]["Valor A (%)"] == ""
    assert records[3]["Valor B (%)"] != ""
    assert records[3]["Diferenca A menos B (p.p.)"] == ""


def test_comparison_and_export_are_stable_under_decimal_traps(reviewed_rows):
    args = (["7170", "7625"], "2024-01", "2024-03", "2023-01", "2023-03")
    expected = group_comparison_csv_bytes(group_comparisons(reviewed_rows, *args))
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 3, 1, -1
        context.traps[Inexact] = context.traps[Rounded] = True
        assert group_comparison_csv_bytes(group_comparisons(reviewed_rows, *args)) == expected


@pytest.mark.parametrize("field,value", [
    ("group_name", "=1+1"), ("retrieved_at", "@SUM(1)"),
    ("raw_sha256", "x\";=1"), ("run_id", "\t=1"), ("mode", "＝1"),
])
def test_group_csv_hostile_provenance_is_rejected(reviewed_rows, field, value):
    row = copy.deepcopy(reviewed_rows[0])
    row[field] = value
    with pytest.raises(ValidationError):
        group_csv_bytes([row])


def test_evolution_accepts_contract_limit_without_global_altair_changes(reviewed_rows):
    import altair as alt

    from radar_inflacao.group_view import evolution_chart

    template = [r for r in reviewed_rows if r["period"] == "2024-01"]
    rows = [{**row, "period": period} for period in periods("2020-01", "2119-12")
            for row in template]
    # Teste de limite sintético: não representa dados futuros do IBGE.
    state = (alt.data_transformers.active, dict(alt.data_transformers.options))
    chart = evolution_chart(rows, "monthly").to_dict()
    assert len(chart["data"]["values"]) == 10800
    assert (alt.data_transformers.active, dict(alt.data_transformers.options)) == state


def test_chart_overflow_is_explicit_without_losing_decimal_csv(reviewed_rows):
    from radar_inflacao.group_view import comparison_chart_data

    rows = [{**r, "monthly": Decimal("999999.999999")} for r in reviewed_rows]
    result = group_comparisons(rows, ["7170"], "2020-01", "2026-10", "2024-01", "2024-03")
    assert result["7170"].a.compounded.is_finite()
    assert comparison_chart_data(result) is None
    csv_data = group_comparison_csv_bytes(result).decode("utf-8-sig")
    assert "Infinity" not in csv_data and "NaN" not in csv_data
    normal = group_comparisons(reviewed_rows, ["7170"], "2024-01", "2024-03",
                              "2023-01", "2023-03")
    assert comparison_chart_data(normal) is not None


@pytest.mark.parametrize("query", [
    "UPDATE group_observation SET weight=-1 WHERE group_id='7170'",
    "UPDATE group_observation SET twelve_month=NULL WHERE period='2024-01-01'",
    "UPDATE group_dimension SET name='=1+1' WHERE id='7170'",
])
def test_group_view_handles_corruption_without_chart_or_download(repository, monkeypatch, query):
    from streamlit.testing.v1 import AppTest

    from radar_inflacao.pipeline import GroupPipeline

    GroupPipeline(repository, ROOT / "sample/groups").demo()
    with repository.locked() as db:
        db.execute(query)
    monkeypatch.setenv("RADAR_DATA_DIR", str(repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="view").set_value("Grupos de despesas").run()
    assert not app.exception
    assert any("Dados dos grupos inválidos" in error.value for error in app.error)
    assert len(app.get("download_button")) == 0
    assert len(app.get("arrow_vega_lite_chart")) == 0


def test_group_view_invalid_provenance_only_blocks_unsafe_exports(repository, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from radar_inflacao.pipeline import GroupPipeline

    GroupPipeline(repository, ROOT / "sample/groups").demo()
    with repository.locked() as db:
        db.execute("UPDATE group_ingestion SET retrieved_at='=1+1'")
    monkeypatch.setenv("RADAR_DATA_DIR", str(repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="view").set_value("Grupos de despesas").run()
    assert not app.exception
    assert any("Exportação dos grupos indisponível" in error.value for error in app.error)
    assert len(app.get("download_button")) == 1
    assert app.get("download_button")[0].label == "Baixar CSV da comparação dos grupos"


def test_group_csv_refuses_non_ascii_month_identifiers(reviewed_rows):
    with pytest.raises(ValidationError):
        group_csv_bytes([{**reviewed_rows[0], "period": "202４-01"}])


def _line(process):
    # Handshake com prazo; uma falha do filho não deixa o teste aguardando para sempre.
    from queue import Queue
    from threading import Thread

    queue = Queue()
    Thread(target=lambda: queue.put(process.stdout.readline()), daemon=True).start()
    return queue.get(timeout=30).strip()


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_real_group_pipeline_commit_or_crash_preserves_snapshot(
    repository, pipeline, tmp_path, finish
):
    import subprocess
    import sys

    from test_groups import GroupFakeSource

    from radar_inflacao.errors import BusyError
    from radar_inflacao.pipeline import GroupPipeline

    pipeline.demo()
    GroupPipeline(repository, ROOT / "sample/groups").demo()
    before = repository.snapshot(include_groups=True)
    from radar_inflacao.quality_report import changes_csv_bytes

    quality_before = repository.quality_snapshot()
    quality_csv = changes_csv_bytes(quality_before)
    args = (list(GROUPS), "2026-10", "2026-10", "2026-09", "2026-09")
    comparison = group_comparisons(before["groups"], *args)
    ranking = group_ranking(before["groups"], list(GROUPS), "2026-10")
    old_exports = (group_csv_bytes(before["groups"]), group_csv_bytes(ranking),
                   group_comparison_csv_bytes(comparison))
    script = r"""
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from test_groups import GroupFakeSource, SAMPLE
from radar_inflacao.storage import Repository
from radar_inflacao.pipeline import GroupPipeline
class PausingRepository(Repository):
    def upsert_groups(self, db, rows, run_id):
        first = super().upsert_groups(db, rows[-9:], run_id)
        print('PARTIAL_TRANSACTION', flush=True)
        sys.stdin.readline()
        rest = super().upsert_groups(db, rows[:-9], run_id)
        return tuple(a+b for a,b in zip(first, rest))
result = GroupPipeline(PausingRepository(Path(sys.argv[1])), SAMPLE,
                       GroupFakeSource(changed=True)).update()
print(result['status'], flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(repository.directory), str(ROOT / "tests")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert _line(process) == "PARTIAL_TRANSACTION"
        with pytest.raises(BusyError):
            repository.snapshot(include_groups=True)
        with pytest.raises(BusyError):
            repository.quality_snapshot()
        assert changes_csv_bytes(quality_before) == quality_csv
        with pytest.raises(BusyError):
            GroupPipeline(repository, ROOT / "sample/groups", GroupFakeSource()).update()
        assert old_exports == (group_csv_bytes(before["groups"]), group_csv_bytes(ranking),
                               group_comparison_csv_bytes(comparison))
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
    after = repository.snapshot(include_groups=True)
    assert after["rows"] == before["rows"]
    assert len(after["groups"]) == len(before["groups"]) == 738
    quality_after = repository.quality_snapshot()
    assert quality_after["total_changes"] == (0 if finish == "crash" else 1)
    assert quality_after["datasets"][1]["latest_attempt"]["stage"] == (
        "PUBLISH" if finish == "crash" else "COMPLETE"
    )
    if finish == "crash":
        assert after["groups"] == before["groups"]
        assert after["groups_history"][0][4] == "INTERRUPTED"
    else:
        updated = group_comparisons(after["groups"], *args)
        assert updated["7170"].a.monthly == Decimal("9.99")
        assert updated["7170"].b == comparison["7170"].b
        assert group_comparison_csv_bytes(updated) != old_exports[2]
        assert group_ranking(after["groups"], list(GROUPS), "2026-10")[0]["group_id"] == "7170"
        assert after["groups_history"][0][4] == "SUCCESS"
    # Nova operação após commit ou morte do escritor: lock liberado, sem duplicações.
    result = GroupPipeline(repository, ROOT / "sample/groups", GroupFakeSource()).update()
    assert result["rows"] == 216
    assert len(repository.snapshot(include_groups=True)["groups"]) == 738


def test_two_group_csv_writers_publish_one_complete_file(reviewed_rows, tmp_path):
    import subprocess
    import sys

    payloads = [group_csv_bytes(filter_group_rows(
        reviewed_rows, codes, "2024-01", "2024-03"
    )) for codes in (["7170"], list(GROUPS))]
    script = r"""
import sys
from pathlib import Path
from radar_inflacao.report import publish_csv
payload = Path(sys.argv[2]).read_bytes()
print('READY', flush=True)
sys.stdin.readline()
try:
    publish_csv(Path(sys.argv[1]), payload)
    print('PUBLISHED', flush=True)
except FileExistsError:
    print('EXISTS', flush=True)
"""
    destination = tmp_path / "groups.csv"
    processes = []
    try:
        for index, payload in enumerate(payloads):
            source = tmp_path / f"input-{index}.csv"
            source.write_bytes(payload)
            processes.append(subprocess.Popen(
                [sys.executable, "-c", script, str(destination), str(source)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        assert all(_line(process) == "READY" for process in processes)
        for process in processes:
            process.stdin.write("\n")
            process.stdin.flush()
        results = [process.communicate(timeout=30) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert sorted(output.strip() for output, _ in results) == ["EXISTS", "PUBLISHED"]
        assert destination.read_bytes() in payloads
        assert not list(tmp_path.glob(".radar-csv-*"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)


def test_historical_null_does_not_allow_missing_field(reviewed_rows):
    row = dict(reviewed_rows[0])
    del row["twelve_month"]
    with pytest.raises(ValidationError):
        group_csv_bytes([row])


@pytest.mark.parametrize("codes", [None, [None], [["7170"]], "7170"])
def test_malformed_group_selection_fails_with_domain_error(reviewed_rows, codes):
    with pytest.raises(ValidationError):
        filter_group_rows(reviewed_rows, codes, "2024-01", "2024-01")
