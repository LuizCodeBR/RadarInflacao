"""CSV da qualidade e das mudanças, tipado e preparado antes da publicação."""

from __future__ import annotations

import csv
import io

from .analysis import validated_rate
from .areas import LOCATIONS
from .audit import DATASETS, FIELDS, MAX_CHANGES
from .audit_contract import STAGES as STAGES
from .audit_contract import run_id as _uuid
from .audit_contract import timestamp as _time
from .audit_contract import validate_filters, validate_reference, validate_run
from .errors import ValidationError
from .groups import GROUPS
from .model import month
from .quality import CHECKS
from .report import _number, _provenance, _text

STATUSES = {"OK", "ERROR", "WARNING", "UNKNOWN", "EMPTY", "INFO"}


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
        if type(item["count"]) is not int or not 0 <= item["count"] <= (
            20400 if code == "areas" else 10800
        ):
            raise ValidationError("Quantidade de registros inválida.")
        attempt, success = item["latest_attempt"], item["latest_success"]
        reference = item["reference"]
        if attempt:
            validate_run(attempt)
        if success:
            validate_run(success, success=True)
        if reference:
            validate_reference(reference)
        if len(item["checks"]) != 4 or {c["code"] for c in item["checks"]} != set(CHECKS):
            raise ValidationError("Relatório exige as quatro verificações distintas.")
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
    total = snapshot["total_changes"]
    if type(total) is not int or total < 0 or total != len(snapshot["changes"]):
        raise ValidationError("Histórico incompleto: total e eventos disponíveis divergem.")
    filters = snapshot["filters"]
    validate_filters(**filters)
    generated = _time(snapshot["generated_at"])
    records, seen = [], set()
    for row in snapshot["changes"]:
        code, group, field = row["dataset"], row["group_id"], row["field"]
        if (
            code not in DATASETS
            or field not in FIELDS
            or row["kind"] not in ("ADDED", "CHANGED")
            or row["run_status"] != "SUCCESS"
            or (code in ("national", "inpc") and (group != "" or field == "weight"))
            or (code == "groups" and group not in GROUPS)
            or (code == "areas" and (group not in LOCATIONS or field == "weight"))
        ):
            raise ValidationError("Mudança inválida no histórico.")
        period = month(row["period"])
        if period < "2020-01":
            raise ValidationError("Mês de mudança fora da cobertura.")
        identity = (code, row["run_id"], period, group, field)
        if identity in seen or row["period_day"] != 1:
            raise ValidationError("Evento duplicado ou data inválida no histórico.")
        seen.add(identity)
        if (
            (filters["dataset"] != "all" and code != filters["dataset"])
            or (filters["kind"] != "all" and row["kind"] != filters["kind"])
            or (filters["group_id"] is not None and group != filters["group_id"])
            or (filters.get("area_key") is not None and group != filters["area_key"])
            or (filters["start"] is not None and period < filters["start"])
            or (filters["end"] is not None and period > filters["end"])
        ):
            raise ValidationError("Evento divergente dos filtros aplicados.")
        old, new = row["old_value"], row["new_value"]
        if row["kind"] == "ADDED":
            if old is not None or row["previous_run_id"] is not None:
                raise ValidationError("Inclusão com valor ou coleta anterior indevidos.")
        else:
            _uuid(row["previous_run_id"])
            if row["previous_run_status"] != "SUCCESS" or row["previous_run_id"] == row["run_id"]:
                raise ValidationError("Vínculo da coleta anterior inválido no histórico.")
        numbers = []
        for index, value in enumerate((old, new)):
            allowed_blank = (index == 0 and row["kind"] == "ADDED") or (
                code in ("groups", "areas")
                and field == "twelve_month"
                and "2020-01" <= period < "2020-12"
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
        if row["kind"] == "CHANGED" and old == new:
            raise ValidationError("Reconferência sem mudança não deve constar como alteração.")
        mode, retrieved, digest, run_id = _provenance(row)
        records.append(
            [
                generated,
                DATASETS[code],
                period,
                group if code == "groups" else "",
                GROUPS[group] if code == "groups" else "Índice geral",
                group if code == "areas" else "",
                LOCATIONS[group] if code == "areas" else "",
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
            "Area ID",
            "Area",
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
