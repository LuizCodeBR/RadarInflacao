import csv
import io
import json

import pytest

from radar_inflacao.cli import main
from radar_inflacao.errors import ValidationError
from radar_inflacao.report import csv_bytes


def test_csv_has_three_official_measures_and_provenance(pipeline, repository):
    pipeline.demo()
    with repository.locked() as db:
        rows = repository.rows(db, "2024-01", "2024-03")
    data = csv_bytes(rows)
    assert data.startswith(b"\xef\xbb\xbf")
    parsed = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert len(parsed) == 4
    assert parsed[1][:4] == ["2024-01", "0,42", "0,42", "4,51"]
    assert all(len(row) == 9 for row in parsed)
    assert "Amostra" in parsed[1]
    assert "\r\n" in data.decode("utf-8-sig")


def test_cli_demo_status_export_and_no_overwrite(tmp_path, capsys):
    directory = tmp_path / "data"
    options = ["--data-dir", str(directory)]
    assert main([*options, "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 82
    assert main([*options, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["modes"] == ["sample"]
    output = tmp_path / "export.csv"
    args = [*options, "export", "--from", "2024-01", "--to", "2024-03", "--output", str(output)]
    assert main(args) == 0
    capsys.readouterr()
    original = output.read_bytes()
    assert main(args) == 2
    assert "já existe" in capsys.readouterr().out
    assert output.read_bytes() == original


def test_empty_export_is_clear(tmp_path, capsys):
    assert (
        main(["--data-dir", str(tmp_path), "export", "--output", str(tmp_path / "empty.csv")]) == 2
    )
    assert "Nenhum mês" in capsys.readouterr().out


def test_inverted_query_range_is_rejected(pipeline, repository):
    pipeline.demo()
    with repository.locked() as db, pytest.raises(ValidationError):
        repository.rows(db, "2024-03", "2024-01")


def test_invalid_cli_date_is_usage_error_without_traceback(tmp_path, capsys):
    with pytest.raises(SystemExit) as result:
        main(
            [
                "--data-dir",
                str(tmp_path),
                "export",
                "--from",
                "wrong",
                "--output",
                str(tmp_path / "file.csv"),
            ]
        )
    assert result.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_csv_preserves_decimal_precision(pipeline, repository):
    from decimal import Decimal

    pipeline.demo()
    rows = repository.snapshot()["rows"][:1]
    rows[0]["monthly"] = Decimal("0.123456")
    text = csv_bytes(rows).decode("utf-8-sig")
    assert "0,123456" in text



def test_comparison_csv_describes_ranges_methods_points_and_unrounded_values():
    from decimal import Decimal

    from radar_inflacao.analysis import compare_periods
    from radar_inflacao.report import comparison_csv_bytes

    rows = [
        {"period": period, "monthly": Decimal(rate),
         "year_to_date": Decimal("2.5"), "twelve_month": Decimal("4.5")}
        for period, rate in [("2024-01", "1"), ("2024-02", "1"), ("2024-03", "2")]
    ]
    comparison = compare_periods(rows, "2024-01", "2024-02", "2024-03", "2024-03")
    raw = comparison_csv_bytes(comparison)
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert len(records) == 4
    first = records[0]
    assert first["Inicio A"] == "2024-01" and first["Fim A"] == "2024-02"
    assert first["Meses A"] == "2" and first["Meses B"] == "1"
    assert Decimal(first["Valor A (%)"].replace(",", ".")) == Decimal("2.01")
    assert Decimal(first["Diferenca A menos B (p.p.)"].replace(",", ".")) == Decimal("0.01")
    assert "estimativa" in first["Metodo"]
    assert "oficial" in records[1]["Metodo"]


def test_comparison_export_preserves_more_than_decimal_default_precision():
    from decimal import Decimal, localcontext

    from radar_inflacao.analysis import compare_periods
    from radar_inflacao.report import comparison_csv_bytes

    rows = [
        {"period": f"2024-{index:02d}", "monthly": Decimal("0.123456"),
         "year_to_date": Decimal("2"), "twelve_month": Decimal("4")}
        for index in range(1, 13)
    ]
    with localcontext() as context:
        context.prec = 6
        comparison = compare_periods(rows, "2024-01", "2024-12", "2024-01", "2024-01")
        text = comparison_csv_bytes(comparison).decode("utf-8-sig")
    first = next(csv.DictReader(io.StringIO(text), delimiter=";"))
    assert Decimal(first["Valor A (%)"].replace(",", ".")) == comparison.a.compounded
