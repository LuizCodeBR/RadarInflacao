"""CSVs nacionais tipados: período com procedência dupla e comparação A/B."""

import csv
import io

from .analysis import format_points, format_rate
from .areas import difference
from .errors import ValidationError
from .indices import INDICES, MEASURES, index_pairs
from .report import _number, _provenance, _validate_group_comparison


def _csv(header, records):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(records)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def index_csv_bytes(indices, start, end):
    pairs = index_pairs(indices, start, end)
    provenance = ("Modo", "Coletado em", "SHA256 resposta", "Coleta ID")
    return _csv(
        [
            "Mes",
            *(f"{label} {MEASURES[f]} (%)" for label in INDICES.values() for f in MEASURES),
            *(f"INPC menos IPCA {MEASURES[f]} (p.p.)" for f in MEASURES),
            *(f"{label} {field}" for label in INDICES.values() for field in provenance),
            "Fonte IPCA",
            "Fonte INPC",
        ],
        [
            [
                pair["period"],
                *(_number(pair[key][f]) for key in INDICES for f in MEASURES),
                *(_number(pair["differences"][f]) for f in MEASURES),
                *[value for key in INDICES for value in _provenance(pair[key])],
                "IBGE / SIDRA 1737",
                "IBGE / SIDRA 1736",
            ]
            for pair in pairs
        ],
    )


def validate_index_comparisons(comparisons):
    if not isinstance(comparisons, dict) or set(comparisons) != set(INDICES):
        raise ValidationError("Comparação exige IPCA e INPC, sem índices adicionais.")
    windows = set()
    for comparison in comparisons.values():
        _validate_group_comparison(comparison)
        if any(s.twelve_month is None for s in (comparison.a, comparison.b)):
            raise ValidationError("Comparação nacional exige todas as medidas oficiais.")
        windows.add((comparison.a.start, comparison.a.end, comparison.b.start, comparison.b.end))
    if len(windows) != 1:
        raise ValidationError("IPCA e INPC devem comparar os mesmos períodos A e B.")


def comparison_records(comparisons, *, display=False):
    validate_index_comparisons(comparisons)
    ipca, inpc = comparisons["ipca"], comparisons["inpc"]
    number = format_rate if display else _number
    points = format_points if display else _number
    return [
        {
            "Indicador": a.label,
            "IPCA A (%)": number(a.a),
            "INPC A (%)": number(b.a),
            "INPC − IPCA em A (p.p.)": points(difference(b.a, a.a)),
            "IPCA B (%)": number(a.b),
            "INPC B (%)": number(b.b),
            "INPC − IPCA em B (p.p.)": points(difference(b.b, a.b)),
            "IPCA A − B (p.p.)": points(a.difference),
            "INPC A − B (p.p.)": points(b.difference),
            "Método": a.method,
        }
        for a, b in zip(ipca.measures, inpc.measures, strict=True)
    ]


def index_comparison_csv_bytes(comparisons):
    records = comparison_records(comparisons)
    c = comparisons["ipca"]
    return _csv(
        [
            "Indicador",
            "Inicio A",
            "Fim A",
            "Meses A",
            "Inicio B",
            "Fim B",
            "Meses B",
            "IPCA A (%)",
            "INPC A (%)",
            "INPC menos IPCA em A (p.p.)",
            "IPCA B (%)",
            "INPC B (%)",
            "INPC menos IPCA em B (p.p.)",
            "IPCA A menos B (p.p.)",
            "INPC A menos B (p.p.)",
            "Metodo",
            "Fonte IPCA",
            "Fonte INPC",
        ],
        [
            [
                r["Indicador"],
                c.a.start,
                c.a.end,
                c.a.count,
                c.b.start,
                c.b.end,
                c.b.count,
                *[r[field] for field in list(r)[1:]],
                "IBGE / SIDRA 1737",
                "IBGE / SIDRA 1736",
            ]
            for r in records
        ],
    )


def inpc_csv_bytes(rows, start, end):
    from .indices import validate_index_rows
    from .model import periods

    validate_index_rows(rows, "inpc")
    selected = sorted([r for r in rows if start <= r["period"] <= end], key=lambda r: r["period"])
    if [r["period"] for r in selected] != periods(start, end):
        raise ValidationError("Não há cobertura completa do INPC para exportar.")
    return _csv(
        [
            "Mes",
            "INPC mensal (%)",
            "INPC no ano (%)",
            "INPC 12 meses (%)",
            "Modo",
            "Coletado em",
            "SHA256 resposta",
            "Coleta ID",
            "Fonte",
        ],
        [
            [r["period"], *(_number(r[f]) for f in MEASURES), *_provenance(r), "IBGE / SIDRA 1736"]
            for r in selected
        ],
    )
