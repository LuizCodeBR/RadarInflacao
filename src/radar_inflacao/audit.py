"""Histórico transacional e consultas coordenadas da central de qualidade."""

from __future__ import annotations

from dataclasses import asdict

from .errors import ValidationError
from .groups import GROUPS
from .model import as_date, month

DATASETS = {"national": "Índice geral", "groups": "Nove grupos"}
FIELDS = {
    "monthly": "Variação mensal",
    "year_to_date": "Acumulado no ano",
    "twelve_month": "Acumulado em 12 meses",
    "weight": "Peso mensal",
}
MAX_CHANGES = 10000


def migrate(db):
    db.execute("BEGIN TRANSACTION")
    try:
        db.execute("""
            CREATE TABLE audit_baseline(
                dataset VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL,
                existing_rows INTEGER NOT NULL
            )
        """)
        for dataset, table in [("national", "observation"), ("groups", "group_observation")]:
            db.execute(
                f"INSERT INTO audit_baseline SELECT ?,current_timestamp,count(*) FROM {table}",
                [dataset],
            )
        db.execute("""
            CREATE TABLE audit_run(
                dataset VARCHAR NOT NULL, run_id VARCHAR NOT NULL,
                stage VARCHAR NOT NULL, metadata_observed_at TIMESTAMPTZ,
                declared_end VARCHAR, metadata_sha256 VARCHAR,
                PRIMARY KEY(dataset,run_id)
            )
        """)
        db.execute("""
            CREATE TABLE data_change(
                dataset VARCHAR NOT NULL, run_id VARCHAR NOT NULL, period DATE NOT NULL,
                group_id VARCHAR NOT NULL, field VARCHAR NOT NULL, kind VARCHAR NOT NULL,
                old_value DECIMAL(14,6), new_value DECIMAL(14,6),
                previous_run_id VARCHAR, recorded_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY(dataset,run_id,period,group_id,field),
                CHECK(dataset IN ('national','groups')),
                CHECK(kind IN ('ADDED','CHANGED')),
                CHECK(field IN ('monthly','year_to_date','twelve_month','weight'))
            )
        """)
        db.execute("UPDATE schema_version SET version=3")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def start_run(db, dataset, run_id):
    db.execute(
        "INSERT INTO audit_run(dataset,run_id,stage) VALUES (?,?,'STARTED')", [dataset, run_id]
    )


def stage(db, dataset, run_id, value):
    db.execute(
        "UPDATE audit_run SET stage=? WHERE dataset=? AND run_id=?", [value, dataset, run_id]
    )


def metadata_seen(db, dataset, run_id, observed_at, end, digest):
    db.execute(
        """UPDATE audit_run SET metadata_observed_at=?,declared_end=?,metadata_sha256=?
                  WHERE dataset=? AND run_id=?""",
        [observed_at, end, digest, dataset, run_id],
    )


def record_changes(db, dataset, current, observations, run_id, recorded_at):
    previous = {(r["period"], r.get("group_id", "")): r for r in current}
    fields = list(FIELDS) if dataset == "groups" else list(FIELDS)[:3]
    changes = []
    for observation in observations:
        row = asdict(observation)
        code = row.get("group_id", "")
        old = previous.get((row["period"], code))
        for field in fields:
            if old is None or old[field] != row[field]:
                changes.append(
                    (
                        dataset,
                        run_id,
                        as_date(row["period"]),
                        code,
                        field,
                        "ADDED" if old is None else "CHANGED",
                        None if old is None else old[field],
                        row[field],
                        None if old is None else old["run_id"],
                        recorded_at,
                    )
                )
    if changes:
        db.executemany("INSERT INTO data_change VALUES (?,?,?,?,?,?,?,?,?,?)", changes)
    return len(changes)


def _records(cursor):
    names = [column[0] for column in cursor.description]
    return [
        dict(
            zip(
                names,
                (value.isoformat() if hasattr(value, "isoformat") else value for value in row),
                strict=True,
            )
        )
        for row in cursor.fetchall()
    ]


def _runs(db, dataset, condition="TRUE", limit=20):
    table = "ingestion" if dataset == "national" else "group_ingestion"
    # Table/condition are internal constants, never user-provided SQL.
    return _records(
        db.execute(
            f"""
        SELECT i.* EXCLUDE(started_at,finished_at),
               strftime(i.started_at,'%Y-%m-%dT%H:%M:%S.%f+00:00') AS started_at,
               strftime(i.finished_at,'%Y-%m-%dT%H:%M:%S.%f+00:00') AS finished_at,
               a.stage,
               strftime(a.metadata_observed_at,'%Y-%m-%dT%H:%M:%S.%f+00:00')
                   AS metadata_observed_at,
               a.declared_end,
               a.metadata_sha256 AS checked_metadata_sha256
        FROM {table} i LEFT JOIN audit_run a ON a.run_id=i.id AND a.dataset=?
        WHERE {condition} ORDER BY i.started_at DESC NULLS LAST, i.id DESC LIMIT ?
    """,
            [dataset, limit],
        )
    )


def read_snapshot(
    repository, db, dataset="all", start=None, end=None, kind="CHANGED", group_id=None
):
    if dataset not in (*DATASETS, "all") or kind not in ("all", "ADDED", "CHANGED"):
        raise ValidationError("Filtro de histórico inválido.")
    if group_id is not None and (dataset != "groups" or group_id not in GROUPS):
        raise ValidationError("O filtro de grupo exige o conjunto Nove grupos e um ID válido.")
    if start is not None:
        month(start)
    if end is not None:
        month(end)
    if start and end and start > end:
        raise ValidationError("O mês inicial precisa ser anterior ou igual ao final.")
    datasets = []
    for code in DATASETS:
        rows = repository.rows(db) if code == "national" else repository.group_rows(db)
        table = "observation" if code == "national" else "group_observation"
        baseline = _records(
            db.execute(
                """SELECT dataset,existing_rows,
                strftime(started_at,'%Y-%m-%dT%H:%M:%S.%f+00:00') AS started_at
                FROM audit_baseline WHERE dataset=?""",
                [code],
            )
        )
        history = _runs(db, code)
        success = _runs(db, code, "i.status='SUCCESS'", 1)
        online = _runs(db, code, "i.mode='live' AND a.declared_end IS NOT NULL", 1)
        reference = online or _runs(db, code, "a.declared_end IS NOT NULL", 1)
        datasets.append(
            {
                "dataset": code,
                "rows": rows,
                "raw_count": db.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
                "baseline": baseline[0],
                "latest_attempt": history[0] if history else None,
                "latest_success": success[0] if success else None,
                "reference": reference[0] if reference else None,
                "history": history,
            }
        )
    where = """(?='all' OR c.dataset=?) AND (?='all' OR c.kind=?)
        AND (? IS NULL OR c.period>=?) AND (? IS NULL OR c.period<=?)
        AND (? IS NULL OR c.group_id=?)"""
    params = [
        dataset,
        dataset,
        kind,
        kind,
        start,
        as_date(start) if start else None,
        end,
        as_date(end) if end else None,
        group_id,
        group_id,
    ]
    total = db.execute(f"SELECT count(*) FROM data_change c WHERE {where}", params).fetchone()[0]
    changes = _records(
        db.execute(
            f"""
        WITH runs AS (
            SELECT 'national' AS dataset,* FROM ingestion
            UNION ALL SELECT 'groups' AS dataset,* FROM group_ingestion
        )
        SELECT c.dataset,c.run_id,strftime(c.period,'%Y-%m') AS period,c.group_id,
               c.field,c.kind,c.old_value,c.new_value,c.previous_run_id,
               strftime(c.recorded_at,'%Y-%m-%dT%H:%M:%S.%f+00:00') AS recorded_at,
               i.mode,i.retrieved_at,i.raw_sha256,i.status AS run_status
        FROM data_change c JOIN runs i ON i.id=c.run_id AND i.dataset=c.dataset
        WHERE {where}
        ORDER BY c.recorded_at DESC,c.run_id,c.dataset,c.period,c.group_id,c.field LIMIT ?
    """,
            [*params, MAX_CHANGES],
        )
    )
    from .storage import utc_now

    return {
        "generated_at": utc_now().isoformat(),
        "datasets": datasets,
        "changes": changes,
        "total_changes": total,
        "truncated": total > MAX_CHANGES,
        "filters": {
            "dataset": dataset,
            "start": start,
            "end": end,
            "kind": kind,
            "group_id": group_id,
        },
    }
