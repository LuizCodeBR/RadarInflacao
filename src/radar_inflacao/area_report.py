"""CSV regional com procedência da área e da referência brasileira."""

import csv
import io

from .areas import (
    AREAS,
    LOCATIONS,
    MEASURES,
    area_ranking,
    difference,
    filter_area_rows,
    selected_areas,
)
from .report import _number, _provenance, _validate_group_comparison

PROVENANCE = ("Modo", "Coletado em", "SHA256 pacote de respostas", "Coleta ID")


def _csv(header, records):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(records)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _value(value):
    return "" if value is None else _number(value)


def area_csv_bytes(rows, keys, start, end, *, ranking=False):
    keys = selected_areas(keys)
    selected = filter_area_rows(rows, keys, start, end)
    brazil = filter_area_rows(rows, ["N1:1"], start, end, brazil=True)
    reference = {r["period"]: r for r in brazil}
    if ranking:
        if start != end:
            from .errors import ValidationError

            raise ValidationError("Ranking regional exige um único mês.")
        selected = area_ranking(rows, keys, start)
    records = []
    for index, row in enumerate(selected, 1):
        code = row["area_key"]
        level, identifier = code.split(":")
        br = reference[row["period"]]
        records.append(
            [
                index if ranking else "",
                row["period"],
                level,
                identifier,
                LOCATIONS[code],
                *(_value(row[f]) for f in MEASURES),
                *(_value(br[f]) for f in MEASURES),
                *(_value(difference(row[f], br[f])) for f in MEASURES),
                *_provenance(row),
                *_provenance(br),
                "IBGE / SIDRA 7060",
            ]
        )
    return _csv(
        [
            "Posicao no ranking mensal",
            "Mes",
            "Nivel territorial",
            "Area ID",
            "Area",
            "Mensal (%)",
            "No ano (%)",
            "12 meses (%)",
            "Brasil mensal (%)",
            "Brasil no ano (%)",
            "Brasil 12 meses (%)",
            "Diferenca mensal (p.p.)",
            "Diferenca no ano (p.p.)",
            "Diferenca 12 meses (p.p.)",
            *PROVENANCE,
            *(f"Brasil {field}" for field in PROVENANCE),
            "Fonte",
        ],
        records,
    )


def area_comparison_csv_bytes(comparisons):
    from .errors import ValidationError

    if not isinstance(comparisons, dict) or "N1:1" not in comparisons:
        raise ValidationError("Comparação exige a referência do Brasil.")
    keys = selected_areas([k for k in comparisons if k != "N1:1"])
    windows = set()
    for comparison in comparisons.values():
        _validate_group_comparison(comparison)
        windows.add((comparison.a.start, comparison.a.end, comparison.b.start, comparison.b.end))
    if len(windows) != 1:
        raise ValidationError("Áreas e Brasil devem usar os mesmos períodos.")
    records = []
    for key in keys:
        comparison = comparisons[key]
        br = comparisons["N1:1"]
        for measure, reference in zip(comparison.measures, br.measures, strict=True):
            records.append(
                [
                    key,
                    AREAS[key],
                    measure.label,
                    comparison.a.start,
                    comparison.a.end,
                    comparison.a.count,
                    _value(measure.a),
                    comparison.b.start,
                    comparison.b.end,
                    comparison.b.count,
                    _value(measure.b),
                    _value(measure.difference),
                    _value(reference.a),
                    _value(reference.b),
                    _value(difference(measure.a, reference.a)),
                    _value(difference(measure.b, reference.b)),
                    measure.method,
                    "IBGE / SIDRA 7060",
                ]
            )
    return _csv(
        [
            "Area ID",
            "Area",
            "Indicador",
            "Inicio A",
            "Fim A",
            "Meses A",
            "A (%)",
            "Inicio B",
            "Fim B",
            "Meses B",
            "B (%)",
            "A menos B (p.p.)",
            "Brasil A (%)",
            "Brasil B (%)",
            "Area menos Brasil A (p.p.)",
            "Area menos Brasil B (p.p.)",
            "Metodo",
            "Fonte",
        ],
        records,
    )
