"""Migração 4→5 e retrato das séries nacionais com vínculo de publicação."""

from .errors import ValidationError

INDEX_TABLES = {
    "ipca": ("observation", "ingestion"),
    "inpc": ("inpc_observation", "inpc_ingestion"),
}


def migrate(db):
    db.execute("BEGIN TRANSACTION")
    try:
        db.execute("CREATE TABLE inpc_ingestion AS SELECT * FROM ingestion WHERE FALSE")
        db.execute("ALTER TABLE inpc_ingestion ADD PRIMARY KEY(id)")
        for field in ("inserted", "updated", "unchanged"):
            db.execute(f"ALTER TABLE inpc_ingestion ALTER {field} SET DEFAULT 0")
        db.execute("ALTER TABLE inpc_ingestion ALTER error SET DEFAULT ''")
        db.execute("""CREATE TABLE inpc_observation(
            period DATE PRIMARY KEY,monthly DECIMAL(14,6) NOT NULL,
            year_to_date DECIMAL(14,6) NOT NULL,twelve_month DECIMAL(14,6) NOT NULL,
            run_id VARCHAR NOT NULL REFERENCES inpc_ingestion(id))""")
        db.execute("""CREATE TABLE inpc_change(
            dataset VARCHAR NOT NULL CHECK(dataset='inpc'),run_id VARCHAR NOT NULL,
            period DATE NOT NULL,group_id VARCHAR NOT NULL CHECK(group_id=''),
            field VARCHAR NOT NULL CHECK(field IN ('monthly','year_to_date','twelve_month')),
            kind VARCHAR NOT NULL CHECK(kind IN ('ADDED','CHANGED')),
            old_value DECIMAL(14,6),new_value DECIMAL(14,6),previous_run_id VARCHAR,
            recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(dataset,run_id,period,group_id,field))""")
        db.execute("INSERT INTO audit_baseline VALUES ('inpc',current_timestamp,0)")
        db.execute("UPDATE schema_version SET version=5")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def index_rows(db, index):
    if not isinstance(index, str) or index not in INDEX_TABLES:
        raise ValidationError("Índice nacional inválido.")
    table, runs = INDEX_TABLES[index]
    values = db.execute(f"""
        SELECT strftime(o.period,'%Y-%m'),o.monthly,o.year_to_date,o.twelve_month,
               i.mode,i.retrieved_at,i.source_url,i.raw_sha256,o.run_id,day(o.period),
               i.status,strftime(i.finished_at,'%Y-%m-%dT%H:%M:%S.%f+00:00'),
               i.start_month,i.end_month
        FROM {table} o LEFT JOIN {runs} i ON i.id=o.run_id ORDER BY o.period
    """).fetchall()
    names = (
        "period",
        "monthly",
        "year_to_date",
        "twelve_month",
        "mode",
        "retrieved_at",
        "source_url",
        "raw_sha256",
        "run_id",
        "period_day",
        "run_status",
        "run_finished_at",
        "run_start",
        "run_end",
    )
    return [dict(zip(names, row, strict=True)) for row in values]
