"""Contrato fechado dos nove grupos nacionais da tabela 7060."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .analysis import _context, compare_periods, validated_rate
from .errors import ValidationError
from .model import BASE_MONTH, month, periods, read_json

GROUPS = {
    "7170": "Alimentação e bebidas",
    "7445": "Habitação",
    "7486": "Artigos de residência",
    "7558": "Vestuário",
    "7625": "Transportes",
    "7660": "Saúde e cuidados pessoais",
    "7712": "Despesas pessoais",
    "7766": "Educação",
    "7786": "Comunicação",
}
GROUP_LABELS = {code: f"{index}.{name}" for index, (code, name) in enumerate(GROUPS.items(), 1)}
GROUP_VARIABLES = {"63", "69", "2265", "66"}


@dataclass(frozen=True)
class GroupObservation:
    period: str
    group_id: str
    monthly: Decimal
    year_to_date: Decimal
    twelve_month: Decimal | None
    weight: Decimal


def validate_group_metadata(raw: bytes) -> str:
    data = read_json(raw)
    try:
        if (
            type(data["id"]) is not int
            or data["id"] != 7060
            or data["periodicidade"]["frequencia"] != "mensal"
            or "N1" not in data["nivelTerritorial"]["Administrativo"]
        ):
            raise ValueError
        variables = data["variaveis"]
        ids = [str(v["id"]) for v in variables]
        if len(ids) != len(set(ids)) or not GROUP_VARIABLES <= set(ids):
            raise ValueError
        if any(v["unidade"] != "%" for v in variables if str(v["id"]) in GROUP_VARIABLES):
            raise ValueError
        classifications = [c for c in data["classificacoes"] if c["id"] == 315]
        if len(classifications) != 1:
            raise ValueError
        categories = classifications[0]["categorias"]
        for code, name in GROUP_LABELS.items():
            matches = [c for c in categories if str(c["id"]) == code]
            if len(matches) != 1 or matches[0]["nome"] != name or matches[0]["nivel"] != 1:
                raise ValueError
        end = str(data["periodicidade"]["fim"])
        if not re.fullmatch(r"[0-9]{6}", end):
            raise ValueError
        result = month(end[:4] + "-" + end[4:])
        if result < BASE_MONTH:
            raise ValueError
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValidationError(
            "Metadados dos grupos mudaram: tabela, medidas ou categorias."
        ) from exc


def parse_group_observations(raw: bytes, expected: list[str]) -> list[GroupObservation]:
    if not expected or expected != periods(expected[0], expected[-1]):
        raise ValidationError("Os meses esperados precisam ser contínuos.")
    payload = read_json(raw)
    values = {code: {} for code in GROUPS}
    try:
        if not isinstance(payload, list) or len(payload) != 4:
            raise ValueError
        variables = set()
        for variable in payload:
            identifier = variable["id"]
            if identifier not in GROUP_VARIABLES or identifier in variables:
                raise ValueError
            variables.add(identifier)
            allowed_units = {"%"}
            if identifier == "2265" and expected[0] < "2020-12":
                allowed_units.add("")  # API omite unidade quando há ausência estrutural.
            if variable["unidade"] not in allowed_units or len(variable["resultados"]) != 9:
                raise ValueError
            seen = set()
            for result in variable["resultados"]:
                classification = result["classificacoes"]
                if len(classification) != 1 or classification[0]["id"] != "315":
                    raise ValueError
                category = classification[0]["categoria"]
                if len(category) != 1:
                    raise ValueError
                code, name = next(iter(category.items()))
                if code not in GROUPS or code in seen or name != GROUP_LABELS[code]:
                    raise ValueError
                seen.add(code)
                if len(result["series"]) != 1:
                    raise ValueError
                series = result["series"][0]
                locality = series["localidade"]
                if locality["id"] != "1" or locality["nivel"]["id"] != "N1":
                    raise ValueError
                data = series["serie"]
                if set(data) != {p.replace("-", "") for p in expected}:
                    raise ValueError
                parsed = {}
                for period in expected:
                    text = data[period.replace("-", "")]
                    if identifier == "2265" and "2020-01" <= period < "2020-12" and text == "...":
                        parsed[period] = None
                        continue
                    if not isinstance(text, str) or not re.fullmatch(
                        r"-?[0-9]{1,6}(?:\.[0-9]{1,6})?", text
                    ):
                        raise ValueError
                    number = validated_rate(Decimal(text))
                    if identifier == "66" and not 0 <= number <= 100:
                        raise ValueError
                    parsed[period] = number
                values[code][identifier] = parsed
        output = [
            GroupObservation(
                period, code, v["63"][period], v["69"][period], v["2265"][period], v["66"][period]
            )
            for code, v in values.items()
            for period in expected
        ]
        with localcontext(_context(32)):
            for period in expected:
                total = sum(r.weight for r in output if r.period == period)
                if abs(total - Decimal(100)) > Decimal("0.05"):
                    raise ValueError
        return sorted(output, key=lambda row: (row.period, list(GROUPS).index(row.group_id)))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValidationError(
            "Grupos inconsistentes: categorias, medidas, meses ou pesos."
        ) from exc


def selected_groups(codes: list[str]) -> list[str]:
    if (
        not isinstance(codes, (list, tuple))
        or not codes
        or any(not isinstance(code, str) or code not in GROUPS for code in codes)
        or len(codes) != len(set(codes))
    ):
        raise ValidationError("Selecione grupos válidos, sem repetição.")
    return [code for code in GROUPS if code in codes]


def validate_group_rows(rows: list[dict]) -> None:
    """Revalida o retrato local antes de análise/CSV; não confia só na coleta passada."""
    if not isinstance(rows, list) or len(rows) > 1200 * len(GROUPS):
        raise ValidationError("Quantidade de registros dos grupos inválida.")
    pairs, weights = set(), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("Registro de grupo inválido.")
        code = row.get("group_id")
        if (
            not isinstance(code, str)
            or code not in GROUPS
            or row.get("group_name") != GROUPS[code]
        ):
            raise ValidationError("Identificação de grupo inválida.")
        period = month(row.get("period"))
        if period < BASE_MONTH or (period, code) in pairs:
            raise ValidationError("Mês inválido ou registro de grupo duplicado.")
        pairs.add((period, code))
        validated_rate(row.get("monthly"))
        validated_rate(row.get("year_to_date"))
        if "twelve_month" not in row:
            raise ValidationError("Registro sem o campo de acumulado em 12 meses.")
        twelve = row["twelve_month"]
        if twelve is not None or not "2020-01" <= period < "2020-12":
            validated_rate(twelve)
        weight = validated_rate(row.get("weight"))
        if not 0 <= weight <= 100:
            raise ValidationError("Peso do grupo fora de 0 a 100%.")
        weights.setdefault(period, []).append(weight)
    with localcontext(_context(32)):
        for values in weights.values():
            if len(values) == len(GROUPS) and abs(sum(values) - Decimal(100)) > Decimal("0.05"):
                raise ValidationError("A soma dos pesos dos nove grupos diverge de 100%.")


def filter_group_rows(rows: list[dict], codes: list[str], start: str, end: str) -> list[dict]:
    codes = selected_groups(codes)
    validate_group_rows(rows)
    expected = periods(start, end)
    selected = [row for row in rows if row["group_id"] in codes and start <= row["period"] <= end]
    pairs = [(row["period"], row["group_id"]) for row in selected]
    if len(pairs) != len(set(pairs)) or set(pairs) != {(p, c) for p in expected for c in codes}:
        raise ValidationError("Não há cobertura completa dos grupos para o período escolhido.")
    return sorted(selected, key=lambda row: (row["period"], codes.index(row["group_id"])))


def group_comparisons(rows, codes, start_a, end_a, start_b, end_b):
    codes = selected_groups(codes)
    a = filter_group_rows(rows, codes, start_a, end_a)
    b = filter_group_rows(rows, codes, start_b, end_b)
    combined = {(r["period"], r["group_id"]): r for r in [*a, *b]}
    return {
        code: compare_periods(
            [r for r in combined.values() if r["group_id"] == code],
            start_a,
            end_a,
            start_b,
            end_b,
            allow_missing_12=True,
        )
        for code in codes
    }


def group_ranking(rows, codes, period):
    selected = filter_group_rows(rows, codes, period, period)
    for row in selected:
        validated_rate(row["monthly"])
    return sorted(
        selected,
        key=lambda row: (row["monthly"].copy_negate(), list(GROUPS).index(row["group_id"])),
    )
