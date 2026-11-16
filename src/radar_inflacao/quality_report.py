"""CSV da qualidade e das mudanças, tipado e preparado antes da publicação."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from uuid import UUID

from .analysis import validated_rate
from .audit import DATASETS, FIELDS, MAX_CHANGES
from .errors import ValidationError
from .groups import GROUPS
from .model import month
from .quality import CHECKS
from .report import _number, _provenance, _text

STATUSES = {"OK", "ERROR", "WARNING", "UNKNOWN", "EMPTY", "INFO"}
STAGES = {
    "STARTED": "Início",
    "SAMPLE": "Leitura da amostra",
    "METADATA": "Metadados",
    "DOWNLOAD": "Download",
    "CONTRACT": "Validação do contrato",
    "ARCHIVE": "Arquivo bruto",
    "PUBLISH": "Publicação",
    "COMPLETE": "Concluída",
}


def _time(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise ValidationError("Data inválida no relatório de qualidade.")
    try:
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValidationError("Data inválida no relatório de qualidade.") from exc
    return value


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Identificação de coleta inválida no histórico.") from exc
    return value


def _csv(header, records):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(records)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def quality_csv_bytes(report):
    generated = _time(report["generated_at"])
    records = []
    for item in report["datasets"]:
        code = item["dataset"]
        if code not in DATASETS or item["grade"] not in STATUSES:
            raise ValidationError("Conjunto ou situação inválido no relatório.")
        if type(item["count"]) is not int or not 0 <= item["count"] <= 10800:
            raise ValidationError("Quantidade de registros inválida.")
        attempt, success = item["latest_attempt"], item["latest_success"]
        reference = item["reference"]
        if attempt and attempt["status"] not in ("SUCCESS", "FAILED", "INTERRUPTED"):
            raise ValidationError("Situação de tentativa inválida.")
        for check in item["checks"]:
            if check["code"] not in CHECKS or check["status"] not in STATUSES:
                raise ValidationError("Verificação de qualidade inválida.")
            records.append(
                [
                    generated,
                    DATASETS[code],
                    item["grade"],
                    item["count"],
                    "" if item["start"] is None else month(item["start"]),
                    "" if item["end"] is None else month(item["end"]),
                    CHECKS[check["code"]],
                    check["status"],
                    _text(check["detail"]),
                    "" if attempt is None else _time(attempt["started_at"]),
                    "" if attempt is None else _text(attempt["status"]),
                    "" if success is None else _time(success["finished_at"]),
                    _time(item["baseline"]["started_at"]),
                    ", ".join(_text(mode) for mode in item["modes"]),
                    "" if attempt is None else STAGES.get(attempt["stage"], "Anterior à central"),
                    "" if attempt is None or not attempt["error"] else _text(attempt["error"]),
                    "" if reference is None else month(reference["declared_end"]),
                    "" if reference is None else _time(reference["metadata_observed_at"]),
                    "" if reference is None else _text(reference["mode"]),
                ]
            )
    return _csv(
        [
            "Relatorio em",
            "Conjunto",
            "Situacao da base",
            "Registros",
            "Inicio",
            "Fim",
            "Verificacao",
            "Resultado",
            "Detalhe",
            "Ultima tentativa",
            "Situacao tentativa",
            "Ultima publicacao concluida",
            "Historico iniciado em",
            "Modos da base",
            "Etapa ultima tentativa",
            "Detalhe ultima tentativa",
            "Ultimo mes declarado",
            "Metadados observados em",
            "Modo dos metadados",
        ],
        records,
    )


def changes_csv_bytes(snapshot):
    if snapshot["truncated"] or len(snapshot["changes"]) > MAX_CHANGES:
        raise ValidationError("Mais de 10000 mudanças; refine os filtros antes de exportar.")
    generated = _time(snapshot["generated_at"])
    records = []
    for row in snapshot["changes"]:
        code, group, field = row["dataset"], row["group_id"], row["field"]
        if (
            code not in DATASETS
            or field not in FIELDS
            or row["kind"] not in ("ADDED", "CHANGED")
            or row["run_status"] != "SUCCESS"
            or (code == "national" and (group != "" or field == "weight"))
            or (code == "groups" and group not in GROUPS)
        ):
            raise ValidationError("Mudança inválida no histórico.")
        period = month(row["period"])
        if period < "2020-01":
            raise ValidationError("Mês de mudança fora da cobertura.")
        old, new = row["old_value"], row["new_value"]
        if row["kind"] == "ADDED":
            if old is not None or row["previous_run_id"] is not None:
                raise ValidationError("Inclusão com valor ou coleta anterior indevidos.")
        else:
            _uuid(row["previous_run_id"])
            if old == new:
                raise ValidationError("Reconferência sem mudança não deve constar como alteração.")
        numbers = []
        for index, value in enumerate((old, new)):
            allowed_blank = (index == 0 and row["kind"] == "ADDED") or (
                code == "groups" and field == "twelve_month" and "2020-01" <= period < "2020-12"
            )
            if value is None:
                if not allowed_blank:
                    raise ValidationError("Valor ausente indevido no histórico.")
                numbers.append("")
            else:
                value = validated_rate(value)
                if field == "weight" and not 0 <= value <= 100:
                    raise ValidationError("Peso inválido no histórico.")
                numbers.append(_number(value))
        mode, retrieved, digest, run_id = _provenance(row)
        records.append(
            [
                generated,
                DATASETS[code],
                period,
                group,
                GROUPS[group] if group else "Índice geral",
                FIELDS[field],
                "Inclusão" if row["kind"] == "ADDED" else "Alteração detectada",
                *numbers,
                _time(row["recorded_at"]),
                mode,
                retrieved,
                digest,
                run_id,
                "" if row["previous_run_id"] is None else _uuid(row["previous_run_id"]),
            ]
        )
    return _csv(
        [
            "Relatorio em",
            "Conjunto",
            "Mes",
            "Grupo ID",
            "Grupo",
            "Indicador",
            "Evento",
            "Valor anterior (%)",
            "Valor novo (%)",
            "Detectado em",
            "Modo",
            "Coletado em",
            "SHA256 resposta",
            "Coleta ID",
            "Coleta anterior ID",
        ],
        records,
    )
