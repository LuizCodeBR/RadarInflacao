"""Demonstração offline identificada e isolada dos dados do usuário."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from filelock import FileLock, Timeout

from .errors import BusyError, ValidationError
from .pipeline import GroupPipeline, Pipeline
from .source import API, GROUP_API, Download, data_url, group_data_url
from .storage import Repository


class SimulationSource:
    def __init__(self, sample: Path, *, grouped=False, invalid=False):
        self.sample, self.grouped, self.invalid = sample, grouped, invalid
        self.api = GROUP_API if grouped else API

    def metadata(self):
        table = "7060" if self.grouped else "1737"
        return Download(
            (self.sample / f"metadata-{table}.json").read_bytes(), self.api + "/metadados"
        )

    def observations(self, start, end):
        table = "7060" if self.grouped else "1737"
        payload = json.loads((self.sample / f"ibge-{table}.json").read_bytes())
        target = payload[0]["resultados"][0]["series"][0]["serie"]
        # Campo sintético propositalmente diferente; nunca é apresentado como coleta do IBGE.
        target[max(target)] = "9.99"
        if self.invalid:
            target.pop(min(target))
        url = group_data_url(start, end) if self.grouped else data_url(start, end)
        return Download(json.dumps(payload, ensure_ascii=False).encode(), url)


def demo_directory(root: Path) -> Path:
    root = root.resolve()
    directory = root / ".cache/quality-demo"
    # O cenário não deve seguir atalhos/junções para outra pasta, mesmo vazia.
    for path in (directory.parent, directory):
        if path.is_symlink() or path.is_junction():
            raise ValidationError("A pasta da demonstração não pode ser um link ou junção.")
    return directory


def _regular_demo_files(directory):
    for name in ("simulation.json", "radar.duckdb", "radar.duckdb.wal", "radar.lock", "raw"):
        path = directory / name
        if path.is_symlink() or path.is_junction() or (path.is_file() and path.stat().st_nlink > 1):
            raise ValidationError("A demonstração contém arquivo ou pasta redirecionado.")


def _existing_demo(directory):
    database = directory / "radar.duckdb"
    if not database.is_file() or database.stat().st_size == 0:
        raise ValidationError("Demonstração sem banco completo; preserve a pasta para conferência.")
    repository = Repository(directory)
    with repository.locked() as db:
        for table in ("ingestion", "group_ingestion"):
            total, simulated, unexpected = db.execute(
                f"""SELECT count(*),
                       count(*) FILTER(WHERE mode='simulation' AND status='SUCCESS'),
                       count(*) FILTER(WHERE mode IS NULL OR mode NOT IN ('sample','simulation'))
                    FROM {table}"""
            ).fetchone()
            if not total or not simulated or unexpected:
                raise ValidationError("Conteúdo incompatível com a demonstração offline.")
    return repository


def prepare_demo(root: Path) -> Repository:
    directory = demo_directory(root)
    directory.parent.mkdir(parents=True, exist_ok=True)
    guard = directory.parent / "quality-demo.lock"
    if guard.is_symlink() or guard.is_junction() or (guard.exists() and guard.stat().st_nlink > 1):
        raise ValidationError("O bloqueio da demonstração não pode ser redirecionado.")
    try:
        with FileLock(directory.parent / "quality-demo.lock", timeout=0):
            _regular_demo_files(directory)
            marker = directory / "simulation.json"
            if marker.exists():
                try:
                    if marker.stat().st_size > 2048:
                        raise ValueError
                    state = json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ValidationError("Marcador da demonstração inválido.") from exc
                if (
                    isinstance(state, dict)
                    and set(state) == {"simulation", "complete"}
                    and state["simulation"] == "quality-v1"
                    and state["complete"] is True
                ):
                    return _existing_demo(directory)
                raise ValidationError("Demonstração incompleta; preserve a pasta para conferência.")
            if directory.exists() and any(directory.iterdir()):
                raise ValidationError("A pasta de demonstração já contém dados não identificados.")
            directory.mkdir(exist_ok=True)
            marker.write_text(
                json.dumps({"simulation": "quality-v1", "complete": False}), encoding="utf-8"
            )
            repository = Repository(directory)
            workers = [
                Pipeline(repository, root / "sample"),
                GroupPipeline(repository, root / "sample/groups"),
            ]
            for worker in workers:
                worker.demo()
                worker.source = SimulationSource(worker.sample_directory, grouped=worker.grouped)
                worker._run("simulation", full=True)
                worker._run("simulation", full=True)  # Reconferência sem nova alteração.
            workers[1].source = SimulationSource(root / "sample/groups", grouped=True, invalid=True)
            try:
                workers[1]._run("simulation", full=True)
            except ValidationError:
                pass  # Falha esperada, com preservação do lote válido anterior.
            else:
                raise ValidationError("O cenário inválido não foi recusado.")
            content = json.dumps({"simulation": "quality-v1", "complete": True})
            temporary = directory / "simulation.tmp"
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(marker)
            return repository
    except Timeout as exc:
        raise BusyError("A demonstração está sendo preparada. Tente novamente.") from exc


def fingerprint(root: Path) -> str:
    """Identificação curta para separar estados dos filtros da base real e da demonstração."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
