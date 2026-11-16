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


def sample_batch(directory: Path) -> Batch:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
        raw = (directory / "ibge-1737.json").read_bytes()
        metadata = (directory / "metadata-1737.json").read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != manifest["sha256"]
            or hashlib.sha256(metadata).hexdigest() != manifest["metadata_sha256"]
        ):
            raise ValidationError("A integridade da amostra divergiu. Baixe o pacote novamente.")
        timestamp = datetime.fromisoformat(manifest["retrieved_at"])
        if timestamp.tzinfo is None or not manifest["data_url"].startswith(
            METADATA_URL.rsplit("/", 1)[0] + "/periodos/"
        ):
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
    def __init__(self, repository: Repository, sample_directory: Path, source=None):
        self.repository = repository
        self.sample_directory = sample_directory
        self.source = source or IbgeSource()

    def demo(self) -> dict:
        return self._run("sample")

    def update(self, *, full: bool = False) -> dict:
        return self._run("live", full=full)

    def ensure_demo(self):
        if not self.repository.snapshot()["rows"]:
            self.demo()

    def _run(self, mode: str, *, full: bool = False) -> dict:
        with self.repository.locked() as db:
            current = self.repository.rows(db)
            if mode == "sample" and any(row["mode"] == "live" for row in current):
                raise ValidationError(
                    "A amostra não substitui dados consultados. Use outra pasta de dados."
                )
            run_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO ingestion(id,started_at,mode,status) VALUES(?,?,?,'RUNNING')",
                [run_id, utc_now(), mode],
            )
            transaction = False
            try:
                if mode == "sample":
                    batch = sample_batch(self.sample_directory)
                else:
                    metadata = self.source.metadata()
                    end = validate_metadata(metadata.raw)
                    if current and end < current[-1]["period"]:
                        raise ValidationError(
                            "A origem está menos recente que a base. Dados preservados."
                        )
                    start = (
                        BASE_MONTH
                        if full or not current
                        else max(BASE_MONTH, next_month(current[-1]["period"], -23))
                    )
                    download = self.source.observations(start, end)
                    batch = Batch(
                        download.raw, metadata.raw, utc_now().isoformat(), download.url, start, end
                    )
                declared_end = validate_metadata(batch.metadata)
                if batch.end > declared_end:
                    raise ValidationError("O período excede a disponibilidade declarada pelo IBGE.")
                rows = parse_observations(batch.raw, periods(batch.start, batch.end))
                raw_sha, raw_file = archive(self.repository.directory, batch.raw, ".json")
                metadata_sha, _ = archive(
                    self.repository.directory, batch.metadata, ".metadata.json"
                )
                db.execute("BEGIN TRANSACTION")
                transaction = True
                counts = self.repository.upsert(db, rows, run_id)
                db.execute(
                    """
                  UPDATE ingestion SET finished_at=?,retrieved_at=?,source_url=?,
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
                    "UPDATE ingestion SET status='FAILED',finished_at=?,error=? WHERE id=?",
                    [utc_now(), detail[:500], run_id],
                )
                if isinstance(exc, RadarError):
                    raise
                raise RadarError("A coleta falhou. A última base válida foi preservada.") from exc
