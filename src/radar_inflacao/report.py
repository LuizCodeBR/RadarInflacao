"""Exportação de medidas oficiais e comparações identificadas."""

from __future__ import annotations

import csv
import io


def csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Mes",
            "IPCA mensal (%)",
            "Acumulado ano (%)",
            "Acumulado 12 meses (%)",
            "Origem",
            "Modo",
            "Coletado em",
            "SHA256 resposta",
            "Coleta ID",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["period"],
                *(
                    format(row[key].normalize(), "f").replace(".", ",")
                    for key in ("monthly", "year_to_date", "twelve_month")
                ),
                "IBGE / SIDRA 1737",
                "Amostra" if row["mode"] == "sample" else "Consulta IBGE",
                row["retrieved_at"],
                row["raw_sha256"],
                row["run_id"],
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")



def comparison_csv_bytes(comparison) -> bytes:
    """Exporta as duas janelas, os métodos e as diferenças sem arredondar para a tela."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Indicador", "Inicio A", "Fim A", "Meses A", "Valor A (%)",
            "Inicio B", "Fim B", "Meses B", "Valor B (%)",
            "Diferenca A menos B (p.p.)", "Metodo", "Fonte",
        ]
    )
    for measure in comparison.measures:
        writer.writerow(
            [
                measure.label, comparison.a.start, comparison.a.end, comparison.a.count,
                format(measure.a, "f").replace(".", ","),
                comparison.b.start, comparison.b.end, comparison.b.count,
                format(measure.b, "f").replace(".", ","),
                format(measure.difference, "f").replace(".", ","),
                measure.method, "IBGE / SIDRA 1737",
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")
