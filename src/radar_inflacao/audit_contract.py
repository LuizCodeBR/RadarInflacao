"""Contratos comuns de leitura da auditoria; sem banco, rede ou interface."""

import re
from datetime import datetime
from uuid import UUID

from .errors import ValidationError
from .groups import GROUPS
from .model import BASE_MONTH, month
from .report import _provenance

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


def timestamp(value):
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


def run_id(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Identificação de coleta inválida no histórico.") from exc
    return value


def validate_filters(dataset="all", start=None, end=None, kind="CHANGED", group_id=None):
    if dataset not in ("national", "groups", "all") or kind not in ("all", "ADDED", "CHANGED"):
        raise ValidationError("Filtro de histórico inválido.")
    if group_id is not None and (
        dataset != "groups" or not isinstance(group_id, str) or group_id not in GROUPS
    ):
        raise ValidationError("O filtro de grupo exige o conjunto Nove grupos e um ID válido.")
    if start is not None:
        month(start)
    if end is not None:
        month(end)
    if start and end and start > end:
        raise ValidationError("O mês inicial precisa ser anterior ou igual ao final.")


def validate_run(run, *, success=False):
    if not isinstance(run, dict):
        raise ValidationError("Identificação de tentativa inválida.")
    run_id(run.get("id"))
    if run.get("mode") not in ("sample", "live", "simulation") or run.get("status") not in (
        ("SUCCESS",) if success else ("SUCCESS", "FAILED", "INTERRUPTED")
    ):
        raise ValidationError("Situação ou modo de tentativa inválido.")
    timestamp(run.get("started_at"))
    timestamp(run.get("finished_at"))
    stage = run.get("stage")
    if stage is not None and (
        stage not in STAGES or (run["status"] == "SUCCESS" and stage != "COMPLETE")
    ):
        raise ValidationError("Etapa incompatível com a tentativa registrada.")


def validate_reference(reference):
    validate_run(reference)
    end = month(reference.get("declared_end"))
    if end < BASE_MONTH:
        raise ValidationError("Disponibilidade anterior à cobertura da base.")
    _provenance(
        {
            "mode": reference.get("mode"),
            "run_id": reference.get("id"),
            "retrieved_at": reference.get("metadata_observed_at"),
            "raw_sha256": reference.get("checked_metadata_sha256"),
        }
    )
    return end
