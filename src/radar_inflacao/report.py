"""Exportação reproduzível de números oficiais; sem soma de percentuais."""

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
