"""Coleta rastreável e publicação atômica; nenhuma atualização agendada."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import audit
from .errors import RadarError, ValidationError
from .model import BASE_MONTH, next_month, parse_observations, periods, validate_metadata
from .source import METADATA_URL, IbgeSource
from .storage import Repository, utc_now


@dataclass(frozen=True)
class Batch:
    raw: bytes
    metadata: bytes
    retrieved_at: str
    source_url: str
    start: str
    end: str


def sample_batch(directory: Path, api: str = METADATA_URL.rsplit("/", 1)[0]) -> Batch:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
        table = api.rsplit("/", 1)[-1]
        raw = (directory / f"ibge-{table}.json").read_bytes()
        metadata = (directory / f"metadata-{table}.json").read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != manifest["sha256"]
            or hashlib.sha256(metadata).hexdigest() != manifest["metadata_sha256"]
        ):
            raise ValidationError("A integridade da amostra divergiu. Baixe o pacote novamente.")
        timestamp = datetime.fromisoformat(manifest["retrieved_at"])
        if timestamp.tzinfo is None or not manifest["data_url"].startswith(api + "/periodos/"):
            raise ValueError("Origem inválida")
        return Batch(
            raw,
            metadata,
            manifest["retrieved_at"],
            manifest["data_url"],
            manifest["from"][:4] + "-" + manifest["from"][4:],
            manifest["to"][:4] + "-" + manifest["to"][4:],
        )
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ValidationError(
            "Não foi possível ler a amostra e sua identificação de origem."
        ) from exc


def archive(directory: Path, raw: bytes, suffix: str) -> tuple[str, str]:
    digest = hashlib.sha256(raw).hexdigest()
    destination = directory / "raw" / (digest + suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValidationError(
                "Um arquivo bruto foi alterado. Preserve a pasta para conferência."
            )
        return digest, str(destination.relative_to(directory))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        return digest, str(destination.relative_to(directory))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Pipeline:
    grouped = False
    dataset = "national"
    run_table = "ingestion"
    metadata_validator = staticmethod(validate_metadata)
    parser = staticmethod(parse_observations)
    source_type = IbgeSource

    def __init__(self, repository: Repository, sample_directory: Path, source=None):
        self.repository = repository
        self.sample_directory = sample_directory
        self.source = source or self.source_type()

    def demo(self) -> dict:
        return self._run("sample")

    def update(self, *, full: bool = False) -> dict:
        return self._run("live", full=full)

    def current_rows(self, db):
        return self.repository.group_rows(db) if self.grouped else self.repository.rows(db)

    def ensure_demo(self):
        with self.repository.locked() as db:
            empty = not self.current_rows(db)
        if empty:
            self.demo()

    def publish(self, db, rows, run_id):
        return self.repository.upsert(db, rows, run_id)

    def _run(self, mode: str, *, full: bool = False) -> dict:
        dataset = self.dataset
        with self.repository.locked() as db:
            current = self.current_rows(db)
            if mode == "sample" and any(row["mode"] in ("live", "simulation") for row in current):
                raise ValidationError(
                    "A amostra não substitui dados consultados ou simulados. "
                    "Use outra pasta de dados."
                )
            run_id = str(uuid.uuid4())
            db.execute(
                f"INSERT INTO {self.run_table}(id,started_at,mode,status) VALUES(?,?,?,'RUNNING')",
                [run_id, utc_now(), mode],
            )
            audit.start_run(db, dataset, run_id)
            transaction = False
            try:
                if mode == "sample":
                    audit.stage(db, dataset, run_id, "SAMPLE")
                    batch = sample_batch(self.sample_directory, self.source_type.api)
                else:
                    audit.stage(db, dataset, run_id, "METADATA")
                    metadata = self.source.metadata()
                    end = self.metadata_validator(metadata.raw)
                    metadata_digest, _ = archive(
                        self.repository.directory, metadata.raw, ".metadata.json"
                    )
                    observed_at = utc_now()
                    audit.metadata_seen(db, dataset, run_id, observed_at, end, metadata_digest)
                    if current and end < current[-1]["period"]:
                        raise ValidationError(
                            "A origem está menos recente que a base. Dados preservados."
                        )
                    start = (
                        BASE_MONTH
                        if full or not current
                        else max(BASE_MONTH, next_month(current[-1]["period"], -23))
                    )
                    audit.stage(db, dataset, run_id, "DOWNLOAD")
                    download = self.source.observations(start, end)
                    batch = Batch(
                        download.raw, metadata.raw, utc_now().isoformat(), download.url, start, end
                    )
                audit.stage(db, dataset, run_id, "CONTRACT")
                declared_end = self.metadata_validator(batch.metadata)
                if mode == "sample":
                    audit.metadata_seen(
                        db,
                        dataset,
                        run_id,
                        datetime.fromisoformat(batch.retrieved_at),
                        declared_end,
                        hashlib.sha256(batch.metadata).hexdigest(),
                    )
                if batch.end > declared_end:
                    raise ValidationError("O período excede a disponibilidade declarada pelo IBGE.")
                rows = self.parser(batch.raw, periods(batch.start, batch.end))
                audit.stage(db, dataset, run_id, "ARCHIVE")
                raw_sha, raw_file = archive(self.repository.directory, batch.raw, ".json")
                metadata_sha, _ = archive(
                    self.repository.directory, batch.metadata, ".metadata.json"
                )
                audit.stage(db, dataset, run_id, "PUBLISH")
                db.execute("BEGIN TRANSACTION")
                transaction = True
                change_count = audit.record_changes(db, dataset, current, rows, run_id, utc_now())
                counts = self.publish(db, rows, run_id)
                db.execute(
                    f"""
                  UPDATE {self.run_table} SET finished_at=?,retrieved_at=?,source_url=?,
                    raw_sha256=?,metadata_sha256=?,raw_file=?,start_month=?,end_month=?,
                    status='SUCCESS',inserted=?,updated=?,unchanged=? WHERE id=?
                """,
                    [
                        utc_now(),
                        batch.retrieved_at,
                        batch.source_url,
                        raw_sha,
                        metadata_sha,
                        raw_file,
                        batch.start,
                        batch.end,
                        *counts,
                        run_id,
                    ],
                )
                audit.stage(db, dataset, run_id, "COMPLETE")
                db.execute("COMMIT")
                transaction = False
                return {
                    "id": run_id,
                    "status": "SUCCESS",
                    "mode": mode,
                    "from": batch.start,
                    "to": batch.end,
                    "rows": len(rows),
                    "inserted": counts[0],
                    "updated": counts[1],
                    "unchanged": counts[2],
                    "raw_sha256": raw_sha,
                    "change_fields": change_count,
                }
            except Exception as exc:
                if transaction:
                    db.execute("ROLLBACK")
                detail = (
                    str(exc)
                    if isinstance(exc, RadarError)
                    else "Falha interna ao publicar a coleta."
                )
                db.execute(
                    f"UPDATE {self.run_table} SET status='FAILED',finished_at=?,error=? WHERE id=?",
                    [utc_now(), detail[:500], run_id],
                )
                if isinstance(exc, RadarError):
                    raise
                raise RadarError("A coleta falhou. A última base válida foi preservada.") from exc


class GroupPipeline(Pipeline):
    from .groups import parse_group_observations, validate_group_metadata
    from .source import GroupSource

    grouped = True
    dataset = "groups"
    run_table = "group_ingestion"
    metadata_validator = staticmethod(validate_group_metadata)
    parser = staticmethod(parse_group_observations)
    source_type = GroupSource


    def publish(self, db, rows, run_id):
        return self.repository.upsert_groups(db, rows, run_id)
