"""Regressões da revisão 0.2.1: limites de exportação, precisão e concorrência."""

import csv
import io
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from radar_inflacao.analysis import compare_periods, format_rate
from radar_inflacao.cli import main
from radar_inflacao.errors import BusyError, ValidationError
from radar_inflacao.report import comparison_csv_bytes, csv_bytes
from radar_inflacao.storage import Repository


@pytest.fixture
def sample_rows(pipeline, repository):
    pipeline.demo()
    return repository.snapshot()["rows"]


def test_csv_does_not_round_under_restricted_decimal_context(sample_rows):
    sample_rows[0]["monthly"] = Decimal("0.123456")
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        text = csv_bytes(sample_rows[:1]).decode("utf-8-sig")
    assert ";0,123456;" in text


def test_calculation_and_display_ignore_ambient_traps_and_exponent_limits(sample_rows):
    with localcontext() as context:
        context.prec = 3
        context.Emax = 1
        context.Emin = -1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        result = compare_periods(sample_rows, "2024-01", "2024-03", "2023-01", "2023-03")
        assert format_rate(result.a.compounded) == "1,42%"
        assert context.prec == 3 and context.Emax == 1 and context.traps[Inexact]


@pytest.mark.parametrize("payload", ["=1+1", "+1+1", "-1+1", "@SUM(1)", "\t=1", "\r=1",
                                     "\n=1", "  =1", "＝1", 'x";=1', "x\x00y"])
@pytest.mark.parametrize("field", ["retrieved_at", "raw_sha256", "run_id"])
def test_monthly_csv_rejects_untrusted_metadata(sample_rows, field, payload):
    sample_rows[0][field] = payload
    with pytest.raises(ValidationError):
        csv_bytes(sample_rows[:1])


@pytest.mark.parametrize("field,value", [
    ("period", "=1"), ("mode", "unknown"), ("monthly", "=1"),
    ("monthly", Decimal("NaN")), ("monthly", Decimal("1E-1000000")),
])
def test_export_rejects_malformed_typed_values(sample_rows, field, value):
    sample_rows[0][field] = value
    with pytest.raises(ValidationError):
        csv_bytes(sample_rows[:1])


def test_numeric_negative_rates_remain_numbers(sample_rows):
    sample_rows[0]["monthly"] = Decimal("-0.123456")
    parsed = list(csv.reader(io.StringIO(csv_bytes(sample_rows[:1]).decode("utf-8-sig")),
                             delimiter=";"))
    assert parsed[1][1] == "-0,123456"


@pytest.mark.parametrize("field", ["label", "method"])
def test_comparison_csv_refuses_formula_text(sample_rows, field):
    comparison = compare_periods(sample_rows, "2024-01", "2024-03", "2023-01", "2023-03")
    measure = replace(comparison.measures[0], **{field: "=1+1"})
    with pytest.raises(ValidationError):
        comparison_csv_bytes(replace(comparison, measures=(measure, *comparison.measures[1:])))


def test_cli_invalid_csv_creates_no_file(sample_rows, repository, tmp_path, capsys):
    with repository.locked() as db:
        db.execute("UPDATE ingestion SET retrieved_at='=1+1'")
    destination = tmp_path / "invalid.csv"
    assert main(["--data-dir", str(repository.directory), "export",
                 "--output", str(destination)]) == 2
    assert "ERROR" in capsys.readouterr().out
    assert not destination.exists()


def test_cli_write_failure_never_publishes_partial_csv(sample_rows, repository, tmp_path,
                                                     monkeypatch, capsys):
    import radar_inflacao.report as report

    destination = tmp_path / "failure.csv"

    def fail_fsync(_):
        assert not destination.exists()
        raise OSError("Falha simulada antes da publicação")

    monkeypatch.setattr(report.os, "fsync", fail_fsync)
    assert main(["--data-dir", str(repository.directory), "export",
                 "--output", str(destination)]) == 2
    assert "Falha simulada" in capsys.readouterr().out
    assert not destination.exists()
    assert not list(tmp_path.glob(".radar-csv-*"))


def test_two_processes_publish_same_destination_without_overwrite(tmp_path):
    # Cada processo prepara bytes diferentes e aguarda a mesma liberação pelo pai.
    script = """
import sys
from pathlib import Path
from radar_inflacao.report import publish_csv
print('READY', flush=True)
sys.stdin.readline()
try:
    publish_csv(Path(sys.argv[1]), sys.argv[2].encode())
    print('PUBLISHED', flush=True)
except FileExistsError:
    print('EXISTS', flush=True)
"""
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(tmp_path / "race.csv"), value],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
        for value in ["first-complete", "second-complete"]
    ]
    try:
        for process in processes:
            assert process.stdout.readline().strip() == "READY"
        for process in processes:
            process.stdin.write("\n")
            process.stdin.flush()
        results = [process.communicate(timeout=15) for process in processes]
        assert sorted(stdout.strip() for stdout, _ in results) == ["EXISTS", "PUBLISHED"]
        assert all(process.returncode == 0 for process in processes), results
        assert (tmp_path / "race.csv").read_bytes() in [b"first-complete", b"second-complete"]
        assert not list(tmp_path.glob(".radar-csv-*"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def test_comparison_snapshot_stays_consistent_during_other_process_commit(sample_rows, repository):
    before = compare_periods(sample_rows, "2024-01", "2024-03", "2023-01", "2023-03")
    old_csv = comparison_csv_bytes(before)
    # Escritor respeita o mesmo lock e para com uma transação ainda não publicada.
    script = """
import sys
from pathlib import Path
from radar_inflacao.storage import Repository
repo = Repository(Path(sys.argv[1]))
with repo.locked() as db:
    db.execute('BEGIN TRANSACTION')
    db.execute("UPDATE observation SET monthly=7.77 WHERE period='2024-03-01'")
    print('UNCOMMITTED', flush=True)
    sys.stdin.readline()
    db.execute('COMMIT')
"""
    with subprocess.Popen([sys.executable, "-c", script, str(repository.directory)],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as process:
        try:
            assert process.stdout.readline().strip() == "UNCOMMITTED"
            with pytest.raises(BusyError):
                Repository(repository.directory).snapshot()
            assert comparison_csv_bytes(before) == old_csv
            assert compare_periods(sample_rows, "2024-01", "2024-03",
                                   "2023-01", "2023-03") == before
        finally:
            _, errors = process.communicate("\n", timeout=15)
        assert process.returncode == 0, errors
    after = compare_periods(repository.snapshot()["rows"], "2024-01", "2024-03",
                            "2023-01", "2023-03")
    assert after.a.monthly == Decimal("7.77")
    assert before.a.monthly == Decimal("0.16")
    assert after.b == before.b
    assert comparison_csv_bytes(after) != old_csv


def test_download_buttons_use_prepared_bytes_without_rerun(tmp_path, monkeypatch):
    from conftest import ROOT
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "app"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    buttons = app.get("download_button")
    assert len(buttons) == 2
    assert all(button.proto.ignore_rerun for button in buttons)



def test_unsupported_atomic_publication_fails_without_leaving_output(tmp_path, monkeypatch):
    from radar_inflacao import report

    def unsupported(*_):
        raise OSError("Sistema de arquivos sem suporte a links")

    monkeypatch.setattr(report.os, "link", unsupported)
    with pytest.raises(OSError, match="sem suporte"):
        report.publish_csv(tmp_path / "output.csv", b"complete")
    assert not (tmp_path / "output.csv").exists()
    assert not list(tmp_path.glob(".radar-csv-*"))


def test_dashboard_handles_invalid_provenance_without_exposing_download(
    tmp_path, monkeypatch, pipeline, repository
):
    from conftest import ROOT
    from streamlit.testing.v1 import AppTest

    pipeline.demo()
    with repository.locked() as db:
        db.execute("UPDATE ingestion SET retrieved_at='=1+1'")
    monkeypatch.setenv("RADAR_DATA_DIR", str(repository.directory))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any("Exportação indisponível" in item.value for item in app.error)
    assert len(app.get("download_button")) == 1  # Só a comparação com textos internos.
    assert len(app.metric) == 6


@pytest.mark.parametrize("value", [Decimal("1E-7"), Decimal("0E-1000000")])
def test_analysis_rejects_values_outside_source_decimal_contract(sample_rows, value):
    sample_rows[0]["monthly"] = value
    with pytest.raises(ValidationError):
        compare_periods(sample_rows, "2020-01", "2020-01", "2020-02", "2020-02")
