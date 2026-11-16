import copy
import json
from decimal import Decimal

import pytest
from conftest import ROOT

from radar_inflacao.errors import ValidationError
from radar_inflacao.model import (
    month,
    next_month,
    parse_observations,
    periods,
    read_json,
    validate_metadata,
)
from radar_inflacao.pipeline import sample_batch


def test_official_sample_and_zero_are_preserved():
    batch = sample_batch(ROOT / "sample")
    rows = parse_observations(batch.raw, periods(batch.start, batch.end))
    assert len(rows) == 82
    january = next(row for row in rows if row.period == "2024-01")
    assert january.monthly == Decimal("0.42")
    assert january.year_to_date == Decimal("0.42")
    assert january.twelve_month == Decimal("4.51")
    assert validate_metadata(batch.metadata) == batch.end


@pytest.mark.parametrize("value", ["2024-00", "2024-13", "24-01", "202401", "2024-1", "x"])
def test_invalid_months(value):
    with pytest.raises(ValidationError):
        month(value)


def test_month_range_handles_year_boundary():
    assert periods("2023-12", "2024-02") == ["2023-12", "2024-01", "2024-02"]
    assert next_month("2024-01", -1) == "2023-12"
    with pytest.raises(ValidationError):
        periods("2024-02", "2024-01")


@pytest.mark.parametrize("invalid", ["-", "...", "X", "NaN", "Infinity", "", "0,42", 0, None, True])
def test_missing_and_malformed_values_are_not_zero(sample_payload, invalid):
    payload = copy.deepcopy(sample_payload)
    payload[0]["resultados"][0]["series"][0]["serie"]["202401"] = invalid
    with pytest.raises(ValidationError):
        parse_observations(json.dumps(payload).encode(), periods("2020-01", "2026-10"))


@pytest.mark.parametrize("case", ["unit", "locality", "variable", "gap", "classification"])
def test_contract_changes_abort_the_whole_batch(sample_payload, case):
    payload = copy.deepcopy(sample_payload)
    if case == "unit":
        payload[0]["unidade"] = "R$"
    elif case == "locality":
        payload[0]["resultados"][0]["series"][0]["localidade"]["id"] = "35"
    elif case == "variable":
        payload[0]["id"] = "69"
    elif case == "gap":
        del payload[0]["resultados"][0]["series"][0]["serie"]["202401"]
    else:
        payload[0]["resultados"][0]["classificacoes"] = [{"id": "1"}]
    with pytest.raises(ValidationError):
        parse_observations(json.dumps(payload).encode(), periods("2020-01", "2026-10"))


def test_negative_and_zero_values_are_valid(sample_payload):
    payload = copy.deepcopy(sample_payload)
    payload[0]["resultados"][0]["series"][0]["serie"]["202401"] = "0.00"
    payload[0]["resultados"][0]["series"][0]["serie"]["202402"] = "-0.10"
    rows = parse_observations(json.dumps(payload).encode(), periods("2020-01", "2026-10"))
    assert next(r for r in rows if r.period == "2024-01").monthly == Decimal("0")
    assert next(r for r in rows if r.period == "2024-02").monthly == Decimal("-0.10")


def test_duplicate_json_keys_and_non_json_fail():
    with pytest.raises(ValidationError):
        read_json(b'{"202401":"0.42","202401":"9.99"}')
    with pytest.raises(ValidationError):
        read_json(b"<html>temporarily unavailable</html>")


def test_metadata_change_fails(metadata):
    changed = json.loads(metadata)
    changed["periodicidade"]["frequencia"] = "anual"
    with pytest.raises(ValidationError):
        validate_metadata(json.dumps(changed).encode())


def test_metadata_validation_is_active_in_optimized_python(tmp_path, metadata):
    import subprocess
    import sys

    file = tmp_path / "invalid.json"
    changed = json.loads(metadata)
    changed["id"] = 1
    file.write_text(json.dumps(changed), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from pathlib import Path; from radar_inflacao.model import validate_metadata; "
            f"validate_metadata(Path({str(file)!r}).read_bytes())",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Metadados do IBGE mudaram" in result.stderr
