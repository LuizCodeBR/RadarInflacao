"""Contrato de dados: Brasil, três medidas oficiais e meses contínuos."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .errors import ValidationError

VARIABLES = {"63": "monthly", "69": "year_to_date", "2265": "twelve_month"}
BASE_MONTH = "2020-01"
MAX_BYTES = 2 * 1024 * 1024


def month(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:19|20|21)\d{2}-(?:0[1-9]|1[0-2])", value
    ):
        raise ValidationError("Mês inválido. Use AAAA-MM.")
    return value


def next_month(value: str, offset: int = 1) -> str:
    year, number = map(int, month(value).split("-"))
    index = year * 12 + number - 1 + offset
    return month(f"{index // 12:04d}-{index % 12 + 1:02d}")


def periods(start: str, end: str) -> list[str]:
    month(start)
    month(end)
    if start > end:
        raise ValidationError("O mês inicial precisa ser anterior ou igual ao final.")
    result, cursor = [], start
    while cursor <= end:
        result.append(cursor)
        if len(result) > 1200:
            raise ValidationError("Intervalo excede 1200 meses.")
        cursor = next_month(cursor)
    return result


def _require(condition):
    if not condition:
        raise ValueError("Contrato da fonte divergente")


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("A fonte retornou chaves duplicadas.")
        result[key] = value
    return result


def read_json(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise ValidationError("Resposta excede o limite de 2 MiB.")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("A fonte não retornou JSON válido.") from exc


def validate_metadata(raw: bytes) -> str:
    data = read_json(raw)
    try:
        _require(isinstance(data, dict) and type(data["id"]) is int and data["id"] == 1737)
        _require(data["periodicidade"]["frequencia"] == "mensal")
        _require(data["nivelTerritorial"]["Administrativo"] == ["N1"])
        variables = data["variaveis"]
        _require(isinstance(variables, list))
        ids = [str(v["id"]) for v in variables]
        _require(len(ids) == len(set(ids)))
        for identifier in VARIABLES:
            _require(any(str(v["id"]) == identifier and v["unidade"] == "%" for v in variables))
        end = str(data["periodicidade"]["fim"])
        _require(re.fullmatch(r"\d{6}", end))
        result = month(end[:4] + "-" + end[4:])
        _require(result >= BASE_MONTH)
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValidationError(
            "Metadados do IBGE mudaram: tabela, frequência, medidas ou unidades."
        ) from exc


@dataclass(frozen=True)
class Observation:
    period: str
    monthly: Decimal
    year_to_date: Decimal
    twelve_month: Decimal


def parse_observations(raw: bytes, expected: list[str]) -> list[Observation]:
    if not expected or expected != periods(expected[0], expected[-1]):
        raise ValidationError("Os meses esperados precisam formar um intervalo contínuo.")
    payload = read_json(raw)
    values: dict[str, dict[str, Decimal]] = {}
    try:
        _require(isinstance(payload, list) and len(payload) == len(VARIABLES))
        for variable in payload:
            identifier = variable["id"]
            _require(identifier in VARIABLES and identifier not in values)
            _require(variable["unidade"] == "%")
            results = variable["resultados"]
            _require(len(results) == 1 and results[0]["classificacoes"] == [])
            series = results[0]["series"]
            _require(len(series) == 1)
            locality = series[0]["localidade"]
            _require(locality["id"] == "1" and locality["nivel"]["id"] == "N1")
            rows = series[0]["serie"]
            _require(isinstance(rows, dict))
            _require(set(rows) == {m.replace("-", "") for m in expected})
            parsed = {}
            for period, value in rows.items():
                _require(isinstance(value, str) and re.fullmatch(r"-?\d{1,6}(?:\.\d{1,6})?", value))
                number = Decimal(value)
                _require(Decimal("-100") <= number <= Decimal("999999.999999"))
                parsed[period[:4] + "-" + period[4:]] = number
            values[identifier] = parsed
        _require(set(values) == set(VARIABLES))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValidationError(
            "Dados inconsistentes: confira medidas, Brasil, unidade %, meses e valores. "
            "Ausência de dado não é tratada como zero."
        ) from exc
    return [Observation(m, values["63"][m], values["69"][m], values["2265"][m]) for m in expected]


def as_date(value: str) -> date:
    return date.fromisoformat(month(value) + "-01")
