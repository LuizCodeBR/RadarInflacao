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


def prepare_demo(root: Path) -> Repository:
    directory = root / ".cache/quality-demo"
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(directory.parent / "quality-demo.lock", timeout=0):
            marker = directory / "simulation.json"
            if marker.exists():
                state = json.loads(marker.read_text(encoding="utf-8"))
                if state == {"simulation": "quality-v1", "complete": True}:
                    return Repository(directory)
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
