"""Verificações explicáveis sobre um único retrato local; nenhuma consulta à rede."""

from __future__ import annotations

from .analysis import validated_rate
from .areas import LOCATIONS, filter_area_rows, validate_area_rows
from .audit import DATASETS
from .audit_contract import validate_reference, validate_run
from .errors import RadarError
from .groups import GROUPS, filter_group_rows, validate_group_rows
from .model import BASE_MONTH, month, periods
from .report import _provenance

CHECKS = {
    "coverage": "Cobertura de meses, grupos e áreas",
    "values": "Taxas, pesos e ausências",
    "provenance": "Identificação da origem",
    "availability": "Disponibilidade na última consulta",
}


def _coverage(rows, grouped, regional=False):
    if not rows:
        return "EMPTY", "Ainda não há observações publicadas."
    months = sorted({month(r.get("period")) for r in rows})
    expected = periods(BASE_MONTH, months[-1])
    if regional:
        filter_area_rows(rows, list(LOCATIONS), BASE_MONTH, months[-1], brazil=True)
    elif grouped:
        filter_group_rows(rows, list(GROUPS), BASE_MONTH, months[-1])
    elif [r["period"] for r in rows] != expected:
        return "ERROR", "A série deve ter todos os meses desde 2020, sem duplicações."
    return "OK", f"{len(expected)} meses completos desde 2020-01."


def _values(rows, grouped, regional=False):
    if not rows:
        return "EMPTY", "Sem dados para verificar."
    if regional:
        validate_area_rows(rows)
        missing = sum(r["twelve_month"] is None for r in rows)
        return "OK", f"Três medidas por área e Brasil; {missing} ausências históricas de 12 meses."
    if grouped:
        validate_group_rows(rows)
        missing = sum(r["twelve_month"] is None for r in rows)
        return "OK", (
            f"Taxas e pesos válidos; {missing} campos de 12 meses na ausência "
            "histórica permitida (jan–nov/2020)."
        )
    for row in rows:
        for field in ("monthly", "year_to_date", "twelve_month"):
            validated_rate(row.get(field))
    return "OK", "Três medidas obrigatórias e taxas decimais válidas."


def _origin(item):
    rows = item["rows"]
    if item["invalid_publications"] or item["invalid_history"]:
        return "ERROR", (
            f"{item['invalid_publications']} observações e {item['invalid_history']} eventos "
            "com publicação, data ou vínculo de coleta inválido. Preserve a base."
        )
    for run in item["history"]:
        validate_run(run)
    if not rows:
        return "EMPTY", "Sem procedência para verificar."
    for row in rows:
        _provenance(row)
    return "OK", "Modo, data com fuso, hash e vínculos das publicações e do histórico válidos."


def _availability(rows, reference):
    if not reference:
        return "UNKNOWN", "Disponibilidade não registrada; faça uma atualização sob demanda."
    end = validate_reference(reference)
    observed = reference["metadata_observed_at"]
    local_end = max((r["period"] for r in rows), default=None)
    if reference["mode"] == "simulation":
        return "INFO", f"Referência simulada até {end}; sem consulta online."
    if reference["mode"] == "sample":
        return "INFO", f"Metadados da amostra até {end}, obtidos em {observed}; sem consulta agora."
    if local_end is None or local_end < end:
        return "WARNING", (
            f"IBGE declarou dados até {end} na consulta de {observed}; "
            "a base local ainda não cobre esse mês."
        )
    if local_end > end:
        return "WARNING", "A referência consultada é anterior ao último mês local; confira a base."
    return "OK", f"Base até {end}, conforme metadados consultados em {observed}."


def build_quality(snapshot):
    result = []
    for item in snapshot["datasets"]:
        rows, grouped = item["rows"], item["dataset"] == "groups"
        regional = item["dataset"] == "areas"
        checks = []
        for code, check in [
            (
                "coverage",
                lambda rows=rows, grouped=grouped, regional=regional: _coverage(
                    rows, grouped, regional
                ),
            ),
            (
                "values",
                lambda rows=rows, grouped=grouped, regional=regional: _values(
                    rows, grouped, regional
                ),
            ),
            ("provenance", lambda item=item: _origin(item)),
            ("availability", lambda rows=rows, item=item: _availability(rows, item["reference"])),
        ]:
            try:
                status, detail = check()
                if code == "coverage" and len(rows) != item["raw_count"]:
                    status, detail = "ERROR", "Há registros sem vínculo válido de grupo ou coleta."
            except RadarError as error:
                status, detail = "ERROR", str(error)
            checks.append({"code": code, "status": status, "detail": detail})
        months = sorted({r["period"] for r in rows})
        statuses = {c["status"] for c in checks}
        grade = (
            "ERROR"
            if "ERROR" in statuses
            else "EMPTY"
            if not rows
            else "WARNING"
            if statuses & {"WARNING", "UNKNOWN"}
            else "OK"
        )
        result.append(
            {
                **item,
                "label": DATASETS[item["dataset"]],
                "checks": checks,
                "grade": grade,
                "count": len(rows),
                "start": months[0] if months else None,
                "end": months[-1] if months else None,
                "modes": sorted({r["mode"] for r in rows}, key=str),
            }
        )
    return {**snapshot, "datasets": result}
