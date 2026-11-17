"""Alinhamento nacional IPCA × INPC, com procedência e cálculos decimais."""

from .analysis import compare_periods, validated_rate
from .areas import difference
from .audit_contract import timestamp
from .errors import ValidationError
from .inpc import inpc_data_url
from .model import BASE_MONTH, month, periods
from .report import _provenance
from .source import data_url

INDICES = {"ipca": "IPCA", "inpc": "INPC"}
MEASURES = {
    "monthly": "Variação mensal",
    "year_to_date": "Acumulado no ano",
    "twelve_month": "Acumulado em 12 meses",
}
URL_BUILDERS = {"ipca": data_url, "inpc": inpc_data_url}


def validate_index_rows(rows, index):
    if not isinstance(index, str) or index not in INDICES:
        raise ValidationError("Índice nacional inválido.")
    if not isinstance(rows, list) or len(rows) > 1200:
        raise ValidationError("Quantidade de registros nacionais inválida.")
    seen, runs, urls = set(), {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("Registro nacional inválido.")
        period = month(row.get("period"))
        if period < BASE_MONTH or period in seen:
            raise ValidationError("Mês nacional fora da cobertura ou duplicado.")
        seen.add(period)
        for field in MEASURES:
            validated_rate(row.get(field))
        origin = _provenance(row)
        start, end = month(row.get("run_start")), month(row.get("run_end"))
        if (
            row.get("run_status") != "SUCCESS"
            or type(row.get("period_day")) is not int
            or row["period_day"] != 1
            or not BASE_MONTH <= start <= period <= end
        ):
            raise ValidationError("Publicação nacional inválida: situação, data ou cobertura.")
        finished = timestamp(row.get("run_finished_at"))
        window = (start, end)
        if window not in urls:
            urls[window] = URL_BUILDERS[index](start, end)
        if row.get("source_url") != urls[window]:
            raise ValidationError("Origem incompatível com o índice nacional informado.")
        identity = (*origin, start, end, finished)
        if runs.setdefault(row["run_id"], identity) != identity:
            raise ValidationError("Procedência divergente para a mesma coleta nacional.")


def validate_indices(indices):
    if not isinstance(indices, dict) or set(indices) != set(INDICES):
        raise ValidationError("A consulta exige IPCA e INPC identificados separadamente.")
    for key in INDICES:
        validate_index_rows(indices[key], key)


def index_pairs(indices, start, end):
    validate_indices(indices)
    expected = periods(start, end)
    by_index = {}
    for key, label in INDICES.items():
        selected = {r["period"]: r for r in indices[key] if start <= r["period"] <= end}
        if set(selected) != set(expected):
            raise ValidationError(
                f"Não há cobertura completa do {label} de {start} a {end}. "
                "O intervalo não foi encurtado e ausências não viram zero."
            )
        by_index[key] = selected
    return [
        {
            "period": p,
            "ipca": by_index["ipca"][p],
            "inpc": by_index["inpc"][p],
            "differences": {
                f: difference(by_index["inpc"][p][f], by_index["ipca"][p][f]) for f in MEASURES
            },
        }
        for p in expected
    ]


def index_comparisons(indices, start, end, bs, be):
    index_pairs(indices, start, end)
    index_pairs(indices, bs, be)
    return {key: compare_periods(indices[key], start, end, bs, be) for key in INDICES}
