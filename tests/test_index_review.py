"""Revisão independente do comparador: publicação, coleta, precisão e concorrência."""

import json
import shutil
from decimal import Decimal

import httpx
import pytest
from conftest import ROOT
from test_indices import SAMPLE, FakeInpc

from radar_inflacao.errors import SourceError, ValidationError
from radar_inflacao.index_report import index_csv_bytes
from radar_inflacao.indices import index_pairs
from radar_inflacao.inpc import INPC_VARIABLES, InpcPipeline, InpcSource
from radar_inflacao.model import VARIABLES, parse_observations, periods
from radar_inflacao.pipeline import Pipeline
from radar_inflacao.source import Download, GroupSource, IbgeSource
from radar_inflacao.storage import Repository


@pytest.fixture(scope="module")
def review_seed(tmp_path_factory):
    repo = Repository(tmp_path_factory.mktemp("review-indices") / "data")
    Pipeline(repo, ROOT / "sample").demo()
    InpcPipeline(repo, SAMPLE).demo()
    return repo.directory


@pytest.fixture
def index_repository(review_seed, tmp_path):
    target = tmp_path / "data"
    shutil.copytree(review_seed, target)
    return Repository(target)


@pytest.fixture
def indices(index_repository):
    return index_repository.snapshot(include_indices=True)["indices"]


@pytest.mark.parametrize("dataset", ["ipca", "inpc"])
@pytest.mark.parametrize("fault", ["query", "window", "timestamp"])
def test_invalid_sample_provenance_never_replaces_published_rows(
    index_repository, tmp_path, dataset, fault
):
    folder = tmp_path / "sample"
    source = ROOT / "sample" if dataset == "ipca" else SAMPLE
    shutil.copytree(source, folder)
    manifest_file = folder / "manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    if fault == "query":
        manifest["data_url"] += "&localidades=N1[2]"
    elif fault == "window":
        manifest["data_url"] = manifest["data_url"].replace("202001|", "")
    else:
        manifest["retrieved_at"] = "2026-11-17 00:46:50+00:00"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    before = index_repository.snapshot(include_indices=True)["indices"]
    changes = index_repository.quality_snapshot(kind="all")["changes"]
    worker_type = Pipeline if dataset == "ipca" else InpcPipeline
    with pytest.raises(ValidationError):
        worker_type(index_repository, folder).demo()
    assert index_repository.snapshot(include_indices=True)["indices"] == before
    assert index_repository.quality_snapshot(kind="all")["changes"] == changes
    with index_repository.locked() as db:
        table = "ingestion" if dataset == "ipca" else "inpc_ingestion"
        status = db.execute(
            f"SELECT status FROM {table} ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        assert status == ("FAILED",)


def test_wrong_live_inpc_url_is_rejected_before_publication(index_repository):
    class WrongOrigin(FakeInpc):
        def observations(self, start, end):
            result = super().observations(start, end)
            return Download(result.raw, result.url.replace("1736", "1737"))

    before = index_repository.snapshot(include_indices=True)["indices"]
    with pytest.raises(ValidationError):
        InpcPipeline(index_repository, SAMPLE, WrongOrigin(changed=True)).update()
    assert index_repository.snapshot(include_indices=True)["indices"] == before
    assert index_repository.quality_snapshot(dataset="inpc", kind="CHANGED")["total_changes"] == 0


@pytest.mark.parametrize("table,mapping", [(1737, VARIABLES), (1736, INPC_VARIABLES)])
def test_measure_mapping_is_independent_of_dictionary_and_payload_order(table, mapping):
    folder = ROOT / "sample" if table == 1737 else SAMPLE
    payload = json.loads((folder / f"ibge-{table}.json").read_bytes())
    expected = periods("2020-01", "2026-10")
    original = parse_observations(json.dumps(payload).encode(), expected, variable_map=mapping)
    reordered = dict(reversed(list(mapping.items())))
    actual = parse_observations(
        json.dumps(list(reversed(payload))).encode(), expected, variable_map=reordered
    )
    assert actual == original
    assert actual[-1].monthly != actual[-1].twelve_month


@pytest.mark.parametrize("measure", ["monthly", "year_to_date", "twelve_month"])
def test_single_month_chart_has_visible_points_for_both_indices(indices, measure):
    from radar_inflacao.index_view import evolution_chart

    pairs = index_pairs(indices, "2026-10", "2026-10")
    spec = evolution_chart(pairs, measure).to_dict()
    assert spec["mark"].get("point")
    assert {r["Índice"] for r in spec["data"]["values"]} == {"IPCA", "INPC"}
    assert [r["Taxa (%)"] for r in spec["data"]["values"]] == [
        float(pairs[0][key][measure]) for key in ("ipca", "inpc")
    ]


@pytest.mark.parametrize("source_type", [IbgeSource, GroupSource, InpcSource])
def test_slow_stream_has_elapsed_time_budget(source_type, monkeypatch):
    from radar_inflacao import source as module

    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    closed, attempts = [], []

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10):
                clock[0] += 12
                yield b" "

        def close(self):
            closed.append(True)

    def handle(request):
        attempts.append(request)
        return httpx.Response(200, stream=SlowStream())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SourceError, match="tempo"):
            source_type(client, lambda _: None).metadata()
    assert clock[0] <= 60
    assert len(attempts) == len(closed) == 1


@pytest.mark.parametrize("source_type", [IbgeSource, GroupSource, InpcSource])
@pytest.mark.parametrize("failure", ["status", "transport"])
def test_retry_does_not_reset_elapsed_budget(source_type, monkeypatch, failure):
    from radar_inflacao import source as module

    clock, calls = [0.0], []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    def handle(request):
        calls.append(request)
        clock[0] += 30
        if failure == "transport":
            raise httpx.ReadTimeout("simulated")
        return httpx.Response(503)

    def sleep(seconds):
        clock[0] += seconds

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SourceError, match="tempo"):
            source_type(client, sleep).metadata()
    assert len(calls) == 2
    assert calls[1].extensions["timeout"]["read"] == 14


def test_default_client_keeps_timeouts_without_injected_client(monkeypatch):
    from radar_inflacao import source as module

    calls = []
    original = httpx.Client

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b"[]")

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(module.httpx, "Client", factory)
    assert InpcSource().metadata().raw == b"[]"
    assert calls[0].extensions["timeout"]["read"] == 15


@pytest.mark.parametrize("index", ["ipca", "inpc"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "=HYPERLINK(\"https://example.org\")"),
        ("retrieved_at", "\t=1"),
        ("raw_sha256", '\";=1'),
        ("run_id", "＠SUM(1)"),
        ("source_url", "https://example.org/\r\n=1"),
        ("monthly", "=1"),
    ],
)
def test_formula_or_control_payload_in_either_index_blocks_both_exports(
    indices, index, field, value
):
    from radar_inflacao.indices import index_comparisons

    next(r for r in indices[index] if r["period"] == "2023-01")[field] = value
    with pytest.raises(ValidationError):
        index_csv_bytes(indices, "2024-01", "2024-03")
    with pytest.raises(ValidationError):
        index_comparisons(indices, "2024-01", "2024-03", "2023-01", "2023-03")


@pytest.mark.parametrize("rate", ["-100", "-99.999999", "0", "0.000001", "999999.999999"])
def test_extreme_compounding_and_csv_match_independent_rational_oracle(indices, rate):
    from decimal import Inexact, Rounded, localcontext
    from fractions import Fraction

    from test_indices import records

    from radar_inflacao.index_report import index_comparison_csv_bytes
    from radar_inflacao.indices import index_comparisons

    for row in indices["inpc"]:
        row["monthly"] = Decimal(rate)
    with localcontext() as context:
        context.prec, context.Emin, context.Emax = 2, -1, 1
        context.traps[Inexact] = context.traps[Rounded] = True
        result = index_comparisons(indices, "2024-01", "2025-12", "2023-01", "2023-03")
        raw = index_comparison_csv_bytes(result)
    oracle = ((1 + Fraction(rate) / 100) ** 24 - 1) * 100
    row = records(raw)[0]
    assert Fraction(row["INPC A (%)"].replace(",", ".")) == oracle
    assert Fraction(row["INPC menos IPCA em A (p.p.)"].replace(",", ".")) == (
        oracle - Fraction(row["IPCA A (%)"].replace(",", "."))
    )


@pytest.mark.parametrize("finish", ["commit", "crash"])
def test_ipca_writer_blocks_inpc_writer_and_new_reader_but_keeps_prepared_csv(
    index_repository, finish
):
    import subprocess
    import sys

    from test_group_review import _line

    from radar_inflacao.errors import BusyError
    from radar_inflacao.index_report import index_comparison_csv_bytes
    from radar_inflacao.indices import index_comparisons

    repo = index_repository
    before = repo.snapshot(include_indices=True)["indices"]

    def exports(snapshot):
        return (
            index_csv_bytes(snapshot, "2026-10", "2026-10"),
            index_comparison_csv_bytes(
                index_comparisons(snapshot, "2026-10", "2026-10", "2026-09", "2026-09")
            ),
        )

    ready = exports(before)
    script = r"""
import os
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from test_pipeline import Source
from radar_inflacao.pipeline import Pipeline
from radar_inflacao.storage import Repository
root=Path(sys.argv[2]).parent
source=Source(json.loads((root/'sample/ibge-1737.json').read_bytes()),
              (root/'sample/metadata-1737.json').read_bytes(),changed=True)
worker=Pipeline(Repository(Path(sys.argv[1])),root/'sample',source)
original=worker.publish
def pause(db,rows,run_id):
    counts=original(db,rows,run_id)
    print('UNCOMMITTED',flush=True)
    if sys.stdin.readline() != 'COMMIT\n':
        os._exit(73)
    return counts
worker.publish=pause
print(worker.update()['status'],flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(repo.directory), str(ROOT / "tests")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _line(process) == "UNCOMMITTED"
        with pytest.raises(BusyError):
            repo.snapshot(include_indices=True)
        with pytest.raises(BusyError):
            InpcPipeline(repo, SAMPLE, FakeInpc(changed=True)).update()
        assert exports(before) == ready
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
    after = repo.snapshot(include_indices=True)["indices"]
    assert after["inpc"] == before["inpc"]
    if finish == "commit":
        assert index_pairs(after, "2026-10", "2026-10")[0]["differences"]["monthly"] == Decimal(
            "-9.77"
        )
        assert repo.quality_snapshot(dataset="national", kind="CHANGED")["total_changes"] == 1
    else:
        assert after == before
        assert repo.snapshot()["history"][0][4] == "INTERRUPTED"
    assert exports(before) == ready


@pytest.mark.parametrize("report", ["period", "comparison"])
def test_two_processes_publish_one_complete_index_csv(indices, tmp_path, report):
    import copy
    import subprocess
    import sys

    from test_group_review import _line

    from radar_inflacao.index_report import index_comparison_csv_bytes
    from radar_inflacao.indices import index_comparisons

    def export(snapshot):
        if report == "period":
            return index_csv_bytes(snapshot, "2026-10", "2026-10")
        return index_comparison_csv_bytes(
            index_comparisons(snapshot, "2026-10", "2026-10", "2026-09", "2026-09")
        )

    revised = copy.deepcopy(indices)
    revised["inpc"][-1]["monthly"] = Decimal("9.99")
    candidates = [export(indices), export(revised)]
    assert candidates[0] != candidates[1]
    target = tmp_path / "report.csv"
    processes = []
    script = r"""
import sys
from pathlib import Path
from radar_inflacao.report import publish_csv
print('READY',flush=True)
sys.stdin.readline()
try:
    publish_csv(Path(sys.argv[2]),Path(sys.argv[1]).read_bytes())
    print('WON',flush=True)
except FileExistsError:
    print('EXISTS',flush=True)
"""
    try:
        for i, candidate in enumerate(candidates):
            source = tmp_path / f"source-{i}.csv"
            source.write_bytes(candidate)
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", script, str(source), str(target)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for process in processes:
            assert _line(process) == "READY"
        for process in processes:
            process.stdin.write("\n")
            process.stdin.flush()
        outcomes = []
        for process in processes:
            out, err = process.communicate(timeout=30)
            assert process.returncode == 0, err
            outcomes.append(out.strip())
        assert sorted(outcomes) == ["EXISTS", "WON"]
        assert target.read_bytes() in candidates
        assert not list(tmp_path.glob(".radar-csv-*.tmp"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)


def test_slow_live_inpc_fails_without_changes_and_releases_database(index_repository, monkeypatch):
    from radar_inflacao import source as module

    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10):
                clock[0] += 12
                yield b" "

    def handler(request):
        if str(request.url).endswith("/metadados"):
            return httpx.Response(200, content=(SAMPLE / "metadata-1736.json").read_bytes())
        return httpx.Response(200, stream=SlowStream())

    before = index_repository.snapshot(include_indices=True)["indices"]
    changes = index_repository.quality_snapshot(kind="all")["changes"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError, match="tempo"):
            InpcPipeline(index_repository, SAMPLE, InpcSource(client)).update()
    assert index_repository.snapshot(include_indices=True)["indices"] == before
    after = index_repository.quality_snapshot(kind="all")
    assert after["changes"] == changes
    latest = after["datasets"][3]["latest_attempt"]
    assert latest["status"] == "FAILED" and latest["stage"] == "DOWNLOAD"


@pytest.mark.parametrize("measure", ["year_to_date", "twelve_month"])
def test_indicator_selection_survives_invalid_period_and_matches_values(
    index_repository, monkeypatch, measure
):
    from streamlit.testing.v1 import AppTest

    from radar_inflacao.analysis import format_rate
    from radar_inflacao.indices import MEASURES

    monkeypatch.setenv("RADAR_DATA_DIR", str(index_repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    app.radio(key="view").set_value("IPCA × INPC").run()
    app.selectbox(key="i_measure").set_value(measure).run()
    app.selectbox(key="i_start").set_value("2026-10")
    app.selectbox(key="i_end").set_value("2026-09").run()
    assert app.error and not app.get("download_button") and not app.exception
    assert app.selectbox(key="i_measure").value == measure
    app.selectbox(key="i_end").set_value("2026-10").run()
    assert not app.exception and app.selectbox(key="i_measure").value == measure
    assert any(s.value == f"{MEASURES[measure]} · 2026-10" for s in app.subheader)
    expected = index_repository.snapshot(include_indices=True)["indices"]
    assert app.metric[0].value == format_rate(expected["ipca"][-1][measure])
    assert app.metric[1].value == format_rate(expected["inpc"][-1][measure])
    assert len(app.get("download_button")) == 2
    assert any("1 mês em ambos" in c.value for c in app.caption)
