"""CSV tipado, validado antes da gravação e publicado sem substituir destinos."""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from .analysis import PeriodComparison, validated_rate
from .errors import ValidationError
from .model import month, periods


def _text(value: str) -> str:
    # Estes campos são identificadores/descrições, nunca fórmulas ou texto multilinha.
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠"))
    ):
        raise ValidationError("Texto inválido para exportação CSV. Confira a origem dos dados.")
    return value


def _number(value: Decimal) -> str:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or len(value.as_tuple().digits) > 20000
        or abs(value.as_tuple().exponent) > 20000
    ):
        raise ValidationError("Número inválido para exportação CSV.")
    # format(f) não usa a precisão do contexto; normalize() poderia arredondar.
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if value.is_zero():
        text = "0"
    return text.replace(".", ",")


def _provenance(row: dict) -> tuple[str, str, str, str]:
    try:
        mode = row["mode"]
        if mode not in ("sample", "live"):
            raise ValueError
        timestamp = _text(row["retrieved_at"])
        if (
            not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
                timestamp,
            )
            or datetime.fromisoformat(timestamp).tzinfo is None
        ):
            raise ValueError
        digest, run_id = _text(row["raw_sha256"]), _text(row["run_id"])
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or str(UUID(run_id)) != run_id:
            raise ValueError
        return "Amostra" if mode == "sample" else "Consulta IBGE", timestamp, digest, run_id
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Procedência inválida para exportação CSV.") from exc


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
                month(row.get("period")),
                *(
                    _number(validated_rate(row.get(key)))
                    for key in ("monthly", "year_to_date", "twelve_month")
                ),
                "IBGE / SIDRA 1737",
                *_provenance(row),
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def comparison_csv_bytes(comparison: PeriodComparison) -> bytes:
    """As taxas negativas são números; textos externos nunca viram fórmulas."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Indicador",
            "Inicio A",
            "Fim A",
            "Meses A",
            "Valor A (%)",
            "Inicio B",
            "Fim B",
            "Meses B",
            "Valor B (%)",
            "Diferenca A menos B (p.p.)",
            "Metodo",
            "Fonte",
        ]
    )
    for summary in (comparison.a, comparison.b):
        if type(summary.count) is not int or not 1 <= summary.count <= 1200:
            raise ValidationError("Quantidade de meses inválida para exportação.")
    for measure in comparison.measures:
        writer.writerow(
            [
                _text(measure.label),
                month(comparison.a.start),
                month(comparison.a.end),
                comparison.a.count,
                _number(measure.a),
                month(comparison.b.start),
                month(comparison.b.end),
                comparison.b.count,
                _number(measure.b),
                _number(measure.difference),
                _text(measure.method),
                "IBGE / SIDRA 1737",
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def publish_csv(destination: Path, data: bytes) -> None:
    """Publica um arquivo completo por link atômico, sem sobrescrita nem janela de corrida."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".radar-csv-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Mesmo diretório/volume. Falha se já existir, inclusive se outro processo venceu.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def group_csv_bytes(rows: list[dict]) -> bytes:
    from .groups import GROUPS

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Mes",
            "Grupo ID",
            "Grupo",
            "IPCA mensal (%)",
            "Acumulado ano (%)",
            "Acumulado 12 meses (%)",
            "Peso mensal (%)",
            "Origem",
            "Modo",
            "Coletado em",
            "SHA256 resposta",
            "Coleta ID",
        ]
    )
    for row in rows:
        code = row.get("group_id")
        if code not in GROUPS or row.get("group_name") != GROUPS[code]:
            raise ValidationError("Grupo inválido para exportação CSV.")
        period = month(row.get("period"))
        twelve = row.get("twelve_month")
        if twelve is None and not "2020-01" <= period < "2020-12":
            raise ValidationError("Acumulado em 12 meses ausente fora da janela histórica.")
        weight = validated_rate(row.get("weight"))
        if not 0 <= weight <= 100:
            raise ValidationError("Peso inválido para exportação.")
        writer.writerow(
            [
                period,
                code,
                GROUPS[code],
                _number(validated_rate(row.get("monthly"))),
                _number(validated_rate(row.get("year_to_date"))),
                "" if twelve is None else _number(validated_rate(twelve)),
                _number(weight),
                "IBGE / SIDRA 7060",
                *_provenance(row),
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def group_comparison_csv_bytes(comparisons: dict[str, PeriodComparison]) -> bytes:
    from .groups import GROUPS, selected_groups

    selected_groups(list(comparisons))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Grupo ID",
            "Grupo",
            "Indicador",
            "Inicio A",
            "Fim A",
            "Meses A",
            "Valor A (%)",
            "Inicio B",
            "Fim B",
            "Meses B",
            "Valor B (%)",
            "Diferenca A menos B (p.p.)",
            "Metodo",
            "Fonte",
        ]
    )
    for code in selected_groups(list(comparisons)):
        comparison = comparisons[code]
        for summary in (comparison.a, comparison.b):
            if type(summary.count) is not int or summary.count != len(
                periods(summary.start, summary.end)
            ):
                raise ValidationError("Quantidade de meses inválida para exportação.")
        for measure in comparison.measures:
            writer.writerow(
                [
                    code,
                    GROUPS[code],
                    _text(measure.label),
                    month(comparison.a.start),
                    month(comparison.a.end),
                    comparison.a.count,
                    "" if measure.a is None else _number(measure.a),
                    month(comparison.b.start),
                    month(comparison.b.end),
                    comparison.b.count,
                    "" if measure.b is None else _number(measure.b),
                    "" if measure.difference is None else _number(measure.difference),
                    _text(measure.method),
                    "IBGE / SIDRA 7060",
                ]
            )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")
