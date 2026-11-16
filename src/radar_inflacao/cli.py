"""python -m radar_inflacao: demo, update, status e export."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .errors import RadarError
from .model import month
from .pipeline import Pipeline
from .report import csv_bytes
from .storage import Repository


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def components(directory: Path | None = None) -> tuple[Repository, Pipeline]:
    root = project_root()
    chosen = directory or Path(os.environ.get("RADAR_DATA_DIR", str(root / "data")))
    repository = Repository(chosen)
    return repository, Pipeline(repository, root / "sample")


def month_argument(value):
    try:
        return month(value)
    except RadarError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Radar da Inflação — dados oficiais do IPCA nacional"
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Pasta independente para banco, brutos e histórico"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Importa a amostra local validada, sem internet")
    update = sub.add_parser("update", help="Consulta o IBGE sob demanda")
    update.add_argument(
        "--full", action="store_true", help="Reconcilia desde 2020, incluindo revisões antigas"
    )
    sub.add_parser("status", help="Mostra cobertura e última execução")
    export = sub.add_parser("export", help="Exporta a base sem substituir arquivo existente")
    export.add_argument("--from", dest="start", type=month_argument)
    export.add_argument("--to", dest="end", type=month_argument)
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repository, pipeline = components(args.data_dir)
        if args.command == "demo":
            result = pipeline.demo()
        elif args.command == "update":
            result = pipeline.update(full=args.full)
        elif args.command == "status":
            snapshot = repository.snapshot()
            rows = snapshot["rows"]
            result = {
                "rows": len(rows),
                "from": rows[0]["period"] if rows else None,
                "to": rows[-1]["period"] if rows else None,
                "modes": sorted({row["mode"] for row in rows}),
                "last_run": snapshot["history"][0] if snapshot["history"] else None,
            }
        else:
            with repository.locked() as db:
                rows = repository.rows(db, args.start, args.end)
            if not rows:
                raise RadarError("Nenhum mês encontrado para exportar.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            try:
                with args.output.open("xb") as handle:
                    handle.write(csv_bytes(rows))
            except FileExistsError as exc:
                raise RadarError("O arquivo já existe. Escolha outro destino.") from exc
            result = {"exported": len(rows), "file": str(args.output.resolve())}
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    except (RadarError, OSError) as exc:
        print(json.dumps({"status": "ERROR", "detail": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
