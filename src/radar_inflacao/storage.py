"""Acesso coordenado ao DuckDB; uma transação publica a coleta completa."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import duckdb
from filelock import FileLock, Timeout

from .errors import BusyError, RadarError, ValidationError
from .model import Observation, as_date, month


class Repository:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "radar.duckdb"
        self.lock_path = self.directory / "radar.lock"

    @contextmanager
    def locked(self):
        try:
            with FileLock(self.lock_path, timeout=0):
                with duckdb.connect(str(self.database)) as connection:
                    connection.execute("SET TimeZone='UTC'")
                    self._schema(connection)
                    yield connection
        except Timeout as exc:
            raise BusyError(
                "A base está em uso por outra operação. Aguarde e tente novamente."
            ) from exc

        except duckdb.Error as exc:
            raise RadarError(
                "Banco local indisponível. Preserve os arquivos e confira a instalação."
            ) from exc

    @staticmethod
    def _schema(db):
        db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        row = db.execute("SELECT version FROM schema_version").fetchall()
        if not row:
            db.execute("INSERT INTO schema_version VALUES (1)")
        elif row not in ([(1,)], [(2,)]):
            raise ValidationError(
                "Esquema de banco incompatível. Preserve a base e use versão compatível."
            )
        db.execute("""
          CREATE TABLE IF NOT EXISTS ingestion(
            id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            mode VARCHAR, retrieved_at VARCHAR, source_url VARCHAR,
            raw_sha256 VARCHAR, metadata_sha256 VARCHAR, raw_file VARCHAR,
            start_month VARCHAR, end_month VARCHAR, status VARCHAR,
            inserted INTEGER DEFAULT 0, updated INTEGER DEFAULT 0, unchanged INTEGER DEFAULT 0,
            error VARCHAR DEFAULT ''
          )
        """)
        db.execute("""
          CREATE TABLE IF NOT EXISTS observation(
            period DATE PRIMARY KEY, monthly DECIMAL(14,6) NOT NULL,
            year_to_date DECIMAL(14,6) NOT NULL, twelve_month DECIMAL(14,6) NOT NULL,
            run_id VARCHAR NOT NULL REFERENCES ingestion(id)
          )
        """)

        if row != [(2,)]:
            Repository._migrate_groups(db)
        db.execute(
            """UPDATE group_ingestion SET status='INTERRUPTED', finished_at=current_timestamp,
                 error='Execução interrompida antes da conclusão.' WHERE status='RUNNING'"""
        )

        db.execute(
            """UPDATE ingestion SET status='INTERRUPTED', finished_at=current_timestamp,
                 error='Execução interrompida antes da conclusão.' WHERE status='RUNNING'"""
        )

    @staticmethod
    def rows(db, start: str | None = None, end: str | None = None) -> list[dict]:
        if start is not None:
            month(start)
        if end is not None:
            month(end)
        if start and end and start > end:
            raise ValidationError("O mês inicial precisa ser anterior ou igual ao final.")
        rows = db.execute(
            """
          SELECT strftime(o.period, '%Y-%m'), o.monthly, o.year_to_date, o.twelve_month,
                 i.mode, i.retrieved_at, i.source_url, i.raw_sha256, o.run_id
          FROM observation o JOIN ingestion i ON i.id=o.run_id
          WHERE (? IS NULL OR o.period>=?) AND (? IS NULL OR o.period<=?)
          ORDER BY o.period
        """,
            [start, as_date(start) if start else None, end, as_date(end) if end else None],
        ).fetchall()
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
        )
        return [dict(zip(names, row, strict=True)) for row in rows]

    def snapshot(self, *, include_groups: bool = False) -> dict:
        with self.locked() as db:
            rows = self.rows(db)
            history = db.execute("""
              SELECT id, cast(started_at as VARCHAR), cast(finished_at as VARCHAR), mode, status,
                     inserted, updated, unchanged, error
              FROM ingestion ORDER BY started_at DESC, id DESC LIMIT 20
            """).fetchall()
            result = {"rows": rows, "history": history}
            if include_groups:
                result["groups"] = self.group_rows(db)
                result["groups_history"] = db.execute("""
                    SELECT id, cast(started_at as VARCHAR), cast(finished_at as VARCHAR), mode,
                           status, inserted, updated, unchanged, error
                    FROM group_ingestion ORDER BY started_at DESC, id DESC LIMIT 20
                """).fetchall()
            return result

    @staticmethod
    def upsert(db, rows: list[Observation], run_id: str) -> tuple[int, int, int]:
        inserted = updated = unchanged = 0
        for row in rows:
            current = db.execute(
                "SELECT monthly,year_to_date,twelve_month FROM observation WHERE period=?",
                [as_date(row.period)],
            ).fetchone()
            values = (row.monthly, row.year_to_date, row.twelve_month)
            if current is None:
                inserted += 1
            elif current == values:
                unchanged += 1
            else:
                updated += 1
            db.execute(
                """
              INSERT INTO observation VALUES(?,?,?,?,?)
              ON CONFLICT(period) DO UPDATE SET monthly=excluded.monthly,
                year_to_date=excluded.year_to_date,twelve_month=excluded.twelve_month,
                run_id=excluded.run_id
            """,
                [as_date(row.period), *values, run_id],
            )
        return inserted, updated, unchanged

    @staticmethod
    def _migrate_groups(db):
        from .groups import GROUPS

        db.execute("BEGIN TRANSACTION")
        try:
            db.execute("""
                CREATE TABLE group_dimension(id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL)
            """)
            db.executemany("INSERT INTO group_dimension VALUES (?,?)", list(GROUPS.items()))
            db.execute("""
                CREATE TABLE group_ingestion(
                    id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
                    mode VARCHAR, retrieved_at VARCHAR, source_url VARCHAR,
                    raw_sha256 VARCHAR, metadata_sha256 VARCHAR, raw_file VARCHAR,
                    start_month VARCHAR, end_month VARCHAR, status VARCHAR,
                    inserted INTEGER DEFAULT 0, updated INTEGER DEFAULT 0,
                    unchanged INTEGER DEFAULT 0, error VARCHAR DEFAULT ''
                )
            """)
            db.execute("""
                CREATE TABLE group_observation(
                    period DATE, group_id VARCHAR REFERENCES group_dimension(id),
                    monthly DECIMAL(14,6) NOT NULL, year_to_date DECIMAL(14,6) NOT NULL,
                    twelve_month DECIMAL(14,6), weight DECIMAL(14,6) NOT NULL,
                    run_id VARCHAR NOT NULL REFERENCES group_ingestion(id),
                    PRIMARY KEY(period, group_id)
                )
            """)
            db.execute("UPDATE schema_version SET version=2")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

    @staticmethod
    def group_rows(db, start=None, end=None) -> list[dict]:
        if start is not None:
            month(start)
        if end is not None:
            month(end)
        if start and end and start > end:
            raise ValidationError("O mês inicial precisa ser anterior ou igual ao final.")
        rows = db.execute(
            """
            SELECT strftime(o.period,'%Y-%m'), o.monthly, o.year_to_date, o.twelve_month,
                   i.mode, i.retrieved_at, i.source_url, i.raw_sha256, o.run_id,
                   o.group_id, g.name, o.weight
            FROM group_observation o
            JOIN group_ingestion i ON i.id=o.run_id JOIN group_dimension g ON g.id=o.group_id
            WHERE (? IS NULL OR o.period>=?) AND (? IS NULL OR o.period<=?)
            ORDER BY o.period, o.group_id
        """,
            [start, as_date(start) if start else None, end, as_date(end) if end else None],
        ).fetchall()
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
            "group_id",
            "group_name",
            "weight",
        )
        return [dict(zip(names, row, strict=True)) for row in rows]

    @staticmethod
    def upsert_groups(db, rows, run_id):
        inserted = updated = unchanged = 0
        for row in rows:
            key = [as_date(row.period), row.group_id]
            current = db.execute(
                "SELECT monthly,year_to_date,twelve_month,weight FROM group_observation "
                "WHERE period=? AND group_id=?",
                key,
            ).fetchone()
            values = (row.monthly, row.year_to_date, row.twelve_month, row.weight)
            if current is None:
                inserted += 1
            elif current == values:
                unchanged += 1
            else:
                updated += 1
            db.execute(
                """
                INSERT INTO group_observation VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(period,group_id) DO UPDATE SET monthly=excluded.monthly,
                    year_to_date=excluded.year_to_date,twelve_month=excluded.twelve_month,
                    weight=excluded.weight,run_id=excluded.run_id
            """,
                [*key, *values, run_id],
            )
        return inserted, updated, unchanged


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
