"""Esquema regional 4 e persistência na mesma conexão coordenada."""

from .areas import LOCATIONS
from .model import as_date


def migrate(db):
    db.execute("BEGIN TRANSACTION")
    try:
        db.execute(
            "CREATE TABLE area_dimension(area_key VARCHAR PRIMARY KEY,name VARCHAR NOT NULL)"
        )
        db.executemany("INSERT INTO area_dimension VALUES (?,?)", list(LOCATIONS.items()))
        db.execute("CREATE TABLE area_ingestion AS SELECT * FROM ingestion WHERE FALSE")
        # CREATE AS não copia a PK; ela é necessária para as referências.
        db.execute("ALTER TABLE area_ingestion ADD PRIMARY KEY(id)")
        for field in ("inserted", "updated", "unchanged"):
            db.execute(f"ALTER TABLE area_ingestion ALTER {field} SET DEFAULT 0")
        db.execute("ALTER TABLE area_ingestion ALTER error SET DEFAULT ''")
        db.execute("""CREATE TABLE area_observation(
            period DATE,area_key VARCHAR REFERENCES area_dimension(area_key),
            monthly DECIMAL(14,6) NOT NULL,year_to_date DECIMAL(14,6) NOT NULL,
            twelve_month DECIMAL(14,6),run_id VARCHAR NOT NULL REFERENCES area_ingestion(id),
            PRIMARY KEY(period,area_key))""")
        db.execute("""CREATE TABLE area_change(
            dataset VARCHAR NOT NULL CHECK(dataset='areas'),run_id VARCHAR NOT NULL,
            period DATE NOT NULL,area_key VARCHAR NOT NULL,field VARCHAR NOT NULL
                CHECK(field IN ('monthly','year_to_date','twelve_month')),
            kind VARCHAR NOT NULL CHECK(kind IN ('ADDED','CHANGED')),
            old_value DECIMAL(14,6),new_value DECIMAL(14,6),previous_run_id VARCHAR,
            recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(dataset,run_id,period,area_key,field))""")
        db.execute("INSERT INTO audit_baseline VALUES ('areas',current_timestamp,0)")
        db.execute("UPDATE schema_version SET version=4")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def rows(db):
    values = db.execute("""
        SELECT strftime(o.period,'%Y-%m'),o.area_key,d.name,o.monthly,o.year_to_date,
               o.twelve_month,i.mode,i.retrieved_at,i.source_url,i.raw_sha256,o.run_id,
               day(o.period),i.status,
               strftime(i.finished_at,'%Y-%m-%dT%H:%M:%S.%f+00:00'),
               i.start_month,i.end_month
        FROM area_observation o LEFT JOIN area_dimension d USING(area_key)
        LEFT JOIN area_ingestion i ON i.id=o.run_id ORDER BY o.period,o.area_key
    """).fetchall()
    names = (
        "period",
        "area_key",
        "area_name",
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


def upsert(db, observations, run_id):
    counts = [0, 0, 0]
    for row in observations:
        key = [as_date(row.period), row.area_key]
        old = db.execute(
            """SELECT monthly,year_to_date,twelve_month FROM area_observation
                          WHERE period=? AND area_key=?""",
            key,
        ).fetchone()
        values = (row.monthly, row.year_to_date, row.twelve_month)
        counts[0 if old is None else 2 if old == values else 1] += 1
        db.execute(
            """INSERT INTO area_observation VALUES (?,?,?,?,?,?)
            ON CONFLICT(period,area_key) DO UPDATE SET monthly=excluded.monthly,
            year_to_date=excluded.year_to_date,twelve_month=excluded.twelve_month,
            run_id=excluded.run_id""",
            [*key, *values, run_id],
        )
    return tuple(counts)
