"""Índice geral das 16 áreas do IPCA e Brasil, tabela 7060."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .analysis import _context, compare_periods, validated_rate
from .errors import ValidationError
from .groups import validate_group_metadata
from .model import BASE_MONTH, month, periods, read_json

AREA_NAMES = {
    "N7:1501": "Belém - PA",
    "N7:2301": "Fortaleza - CE",
    "N7:2601": "Recife - PE",
    "N7:2901": "Salvador - BA",
    "N7:3101": "Belo Horizonte - MG",
    "N7:3201": "Grande Vitória - ES",
    "N7:3301": "Rio de Janeiro - RJ",
    "N7:3501": "São Paulo - SP",
    "N7:4101": "Curitiba - PR",
    "N7:4301": "Porto Alegre - RS",
    "N6:1200401": "Rio Branco - AC",
    "N6:2111300": "São Luís - MA",
    "N6:2800308": "Aracaju - SE",
    "N6:5002704": "Campo Grande - MS",
    "N6:5208707": "Goiânia - GO",
    "N6:5300108": "Brasília - DF",
}


def _area_label(key, name):
    kind = (
        "região metropolitana"
        if key.startswith("N7:")
        else "área pesquisada no DF"
        if key == "N6:5300108"
        else "município"
    )
    return f"{name} · {kind}"


AREAS = {key: _area_label(key, name) for key, name in AREA_NAMES.items()}
LOCATIONS = {"N1:1": "Brasil", **AREAS}
SOURCE_NAMES = {"N1:1": "Brasil", **AREA_NAMES}
MEASURES = {
    "monthly": "Variação mensal",
    "year_to_date": "Acumulado no ano",
    "twelve_month": "Acumulado em 12 meses",
}
VARIABLES = {"63": "monthly", "69": "year_to_date", "2265": "twelve_month"}


@dataclass(frozen=True)
class AreaObservation:
    period: str
    area_key: str
    monthly: Decimal
    year_to_date: Decimal
    twelve_month: Decimal | None


def windows(start, end):
    months = periods(start, end)
    return [(months[i], months[min(i + 23, len(months) - 1)]) for i in range(0, len(months), 24)]


def area_data_url(start, end):
    from .source import GROUP_API

    sequence = "|".join(p.replace("-", "") for p in periods(start, end))
    localities = "|".join(
        f"{level}[{','.join(k.split(':')[1] for k in LOCATIONS if k.startswith(level + ':'))}]"
        for level in ("N1", "N7", "N6")
    )
    return (
        f"{GROUP_API}/periodos/{sequence}/variaveis/63|69|2265"
        f"?localidades={localities}&classificacao=315[7169]"
    )


def validate_area_metadata(raw):
    end = validate_group_metadata(raw)
    data = read_json(raw)
    try:
        if not {"N1", "N6", "N7"} <= set(data["nivelTerritorial"]["Administrativo"]):
            raise ValueError
        category = [c for c in data["classificacoes"][0]["categorias"] if c["id"] == 7169]
        if len(category) != 1 or category[0]["nome"] != "Índice geral" or category[0]["nivel"] != 0:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            "Metadados regionais incompatíveis: territórios ou índice geral."
        ) from exc
    return end


def parse_area_response(raw, expected):
    if not expected or expected != periods(expected[0], expected[-1]) or len(expected) > 24:
        raise ValidationError("Lote regional exige de 1 a 24 meses contínuos.")
    data = read_json(raw)
    values = {key: {} for key in LOCATIONS}
    try:
        if not isinstance(data, list) or len(data) != 3:
            raise ValueError
        seen_variables = set()
        for variable in data:
            identifier = variable["id"]
            if identifier not in VARIABLES or identifier in seen_variables:
                raise ValueError
            seen_variables.add(identifier)
            units = {"%", ""} if identifier == "2265" and expected[0] < "2020-12" else {"%"}
            if variable["unidade"] not in units or len(variable["resultados"]) != 1:
                raise ValueError
            result = variable["resultados"][0]
            classifications = result["classificacoes"]
            if (
                len(classifications) != 1
                or classifications[0]["id"] != "315"
                or classifications[0]["categoria"] != {"7169": "Índice geral"}
            ):
                raise ValueError
            seen = set()
            for series in result["series"]:
                location = series["localidade"]
                key = location["nivel"]["id"] + ":" + location["id"]
                if (
                    key not in LOCATIONS
                    or key in seen
                    or location["nome"]
                    not in (
                        SOURCE_NAMES[key],
                        re.sub(r" - ([A-Z]{2})$", r" (\1)", SOURCE_NAMES[key]),
                    )
                ):
                    raise ValueError
                seen.add(key)
                source = series["serie"]
                if set(source) != {p.replace("-", "") for p in expected}:
                    raise ValueError
                for period in expected:
                    text = source[period.replace("-", "")]
                    if identifier == "2265" and period < "2020-12" and text == "...":
                        number = None
                    else:
                        if not isinstance(text, str) or not re.fullmatch(
                            r"-?[0-9]{1,6}(?:\.[0-9]{1,6})?", text
                        ):
                            raise ValueError
                        number = validated_rate(Decimal(text))
                    values[key].setdefault(period, {})[VARIABLES[identifier]] = number
            if seen != set(LOCATIONS):
                raise ValueError
        return [AreaObservation(p, key, **values[key][p]) for p in expected for key in LOCATIONS]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(
            "Lote regional inválido: medidas, áreas, nomes, meses ou valores divergentes."
        ) from exc


def bundle_bytes(downloads):
    data = {
        "format": "radar-areas-v1",
        "parts": [
            {
                "url": d.url,
                "sha256": hashlib.sha256(d.raw).hexdigest(),
                "body": d.raw.decode("utf-8"),
            }
            for d in downloads
        ],
    }
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    read_json(raw)  # Limite total de 2 MiB também para o pacote de respostas.
    return raw


def parse_area_bundle(raw, expected):
    if not expected or expected != periods(expected[0], expected[-1]):
        raise ValidationError("Período regional inválido.")
    data = read_json(raw)
    try:
        chunks = windows(expected[0], expected[-1])
        if data["format"] != "radar-areas-v1" or len(data["parts"]) != len(chunks):
            raise ValueError
        output = []
        for part, (start, end) in zip(data["parts"], chunks, strict=True):
            body = part["body"].encode("utf-8")
            if (
                part["url"] != area_data_url(start, end)
                or hashlib.sha256(body).hexdigest() != part["sha256"]
            ):
                raise ValueError
            output.extend(parse_area_response(body, periods(start, end)))
        return output
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Pacote regional incompleto ou com identificação inválida.") from exc


def selected_areas(keys, *, brazil=False):
    allowed = LOCATIONS if brazil else AREAS
    if (
        not isinstance(keys, (list, tuple))
        or not keys
        or any(not isinstance(k, str) or k not in allowed for k in keys)
        or len(keys) != len(set(keys))
    ):
        raise ValidationError("Selecione áreas válidas, sem repetição.")
    return [key for key in allowed if key in keys]


def validate_area_rows(rows):
    if not isinstance(rows, list) or len(rows) > 1200 * len(LOCATIONS):
        raise ValidationError("Quantidade de registros regionais inválida.")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("Registro regional inválido.")
        key = row.get("area_key")
        if (
            not isinstance(key, str)
            or key not in LOCATIONS
            or row.get("area_name") != LOCATIONS[key]
        ):
            raise ValidationError("Identificação de área inválida.")
        period = month(row.get("period"))
        if period < BASE_MONTH or (period, key) in seen:
            raise ValidationError("Mês regional inválido ou duplicado.")
        seen.add((period, key))
        for field in MEASURES:
            if field not in row:
                raise ValidationError("Medida regional ausente.")
            value = row[field]
            if field == "twelve_month" and value is None and period < "2020-12":
                continue
            validated_rate(value)


def filter_area_rows(rows, keys, start, end, *, brazil=False):
    keys = selected_areas(keys, brazil=brazil)
    validate_area_rows(rows)
    expected = {(p, k) for p in periods(start, end) for k in keys}
    selected = [r for r in rows if start <= r["period"] <= end and r["area_key"] in keys]
    if {(r["period"], r["area_key"]) for r in selected} != expected:
        raise ValidationError("Não há cobertura completa das áreas no período escolhido.")
    return sorted(selected, key=lambda r: (r["period"], keys.index(r["area_key"])))


def difference(value, reference):
    if value is None or reference is None:
        return None
    with localcontext(
        _context(
            max(len(value.as_tuple().digits), len(reference.as_tuple().digits))
            + abs(value.adjusted() - reference.adjusted())
            + abs(value.as_tuple().exponent - reference.as_tuple().exponent)
            + 8
        )
    ):
        return value - reference


def area_ranking(rows, keys, period):
    selected = filter_area_rows(rows, keys, period, period)
    brazil = filter_area_rows(rows, ["N1:1"], period, period, brazil=True)[0]
    ranked = sorted(
        selected, key=lambda r: (r["monthly"].copy_negate(), list(AREAS).index(r["area_key"]))
    )
    return [
        {**r, "brazil": brazil, "differences": {f: difference(r[f], brazil[f]) for f in MEASURES}}
        for r in ranked
    ]


def area_comparisons(rows, keys, start, end, bs, be):
    keys = selected_areas(keys)
    a = filter_area_rows(rows, ["N1:1", *keys], start, end, brazil=True)
    b = filter_area_rows(rows, ["N1:1", *keys], bs, be, brazil=True)
    combined = {(r["period"], r["area_key"]): r for r in [*a, *b]}
    return {
        key: compare_periods(
            [r for r in combined.values() if r["area_key"] == key],
            start,
            end,
            bs,
            be,
            allow_missing_12=True,
        )
        for key in ["N1:1", *keys]
    }
