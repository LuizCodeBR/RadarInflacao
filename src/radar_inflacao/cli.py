"""python -m radar_inflacao: demo, update, status e export."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .errors import RadarError, ValidationError
from .groups import GROUPS, filter_group_rows
from .model import month
from .pipeline import GroupPipeline, Pipeline
from .report import csv_bytes, group_csv_bytes, publish_csv
from .storage import Repository


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def components(
    directory: Path | None = None, *, allow_simulation: bool = False
) -> tuple[Repository, Pipeline]:
    root = project_root()
    chosen = directory or Path(os.environ.get("RADAR_DATA_DIR", str(root / "data")))
    reserved = (root / ".cache/quality-demo").resolve()
    resolved = chosen.resolve()
    if not allow_simulation and (resolved == reserved or resolved.is_relative_to(reserved)):
        raise ValidationError(
            "A demonstração não pode ser a base principal nem receber atualizações. "
            "Use a central para abrir o exemplo ou outra pasta para seus dados."
        )
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
    demo = sub.add_parser("demo", help="Importa as amostras locais validadas, sem internet")
    demo.add_argument("--dataset", choices=["all", "national", "groups"], default="all")
    update = sub.add_parser("update", help="Consulta o IBGE sob demanda")
    update.add_argument("--dataset", choices=["all", "national", "groups"], default="all")
    update.add_argument(
        "--full", action="store_true", help="Reconcilia desde 2020, incluindo revisões antigas"
    )
    sub.add_parser("quality", help="Mostra o relatório local de qualidade, sem consultar a rede")
    sub.add_parser("quality-demo", help="Cria demonstração offline em .cache/quality-demo")
    quality_export = sub.add_parser("quality-export", help="Exporta qualidade ou mudanças em CSV")
    quality_export.add_argument("--report", choices=["summary", "changes"], default="summary")
    quality_export.add_argument("--dataset", choices=["all", "national", "groups"], default="all")
    quality_export.add_argument("--kind", choices=["all", "ADDED", "CHANGED"], default="CHANGED")
    quality_export.add_argument("--group", choices=list(GROUPS))
    quality_export.add_argument("--from", dest="start", type=month_argument)
    quality_export.add_argument("--to", dest="end", type=month_argument)
    quality_export.add_argument("--output", type=Path, required=True)
    sub.add_parser("status", help="Mostra cobertura e última execução")
    export = sub.add_parser("export", help="Exporta a base sem substituir arquivo existente")
    export.add_argument("--dataset", choices=["national", "groups"], default="national")
    export.add_argument("--groups", nargs="+", choices=list(GROUPS), default=list(GROUPS))
    export.add_argument("--from", dest="start", type=month_argument)
    export.add_argument("--to", dest="end", type=month_argument)
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "quality-demo":
            if args.data_dir is not None:
                raise RadarError(
                    "A demonstração usa somente .cache/quality-demo; omita --data-dir."
                )
            from .simulation import prepare_demo

            demo_repository = prepare_demo(project_root())
            print(json.dumps({"simulation": True, "directory": str(demo_repository.directory)}))
            return 0
        repository, pipeline = components(
            args.data_dir,
            allow_simulation=args.command in ("quality", "quality-export", "status", "export"),
        )
        if args.command in ("quality", "quality-export"):
            from .quality import build_quality
            from .quality_report import changes_csv_bytes, quality_csv_bytes

            filters = (
                {}
                if args.command == "quality"
                else {
                    "dataset": args.dataset,
                    "kind": args.kind,
                    "group_id": args.group,
                    "start": args.start,
                    "end": args.end,
                }
            )
            report = build_quality(repository.quality_snapshot(**filters))
            if args.command == "quality":
                result = {
                    "generated_at": report["generated_at"],
                    "datasets": [
                        {k: v for k, v in item.items() if k not in ("rows", "history")}
                        for item in report["datasets"]
                    ],
                    "changes_found": report["total_changes"],
                }
            else:
                data = (
                    quality_csv_bytes(report)
                    if args.report == "summary"
                    else changes_csv_bytes(report)
                )
                try:
                    publish_csv(args.output, data)
                except FileExistsError as exc:
                    raise RadarError("O arquivo já existe. Escolha outro destino.") from exc
                result = {"file": str(args.output.resolve()), "report": args.report}
        elif args.command in ("demo", "update"):
            group_pipeline = GroupPipeline(repository, project_root() / "sample/groups")
            workers = (
                [("national", pipeline), ("groups", group_pipeline)]
                if args.dataset == "all"
                else [(args.dataset, pipeline if args.dataset == "national" else group_pipeline)]
            )
            results, failures = {}, {}
            for label, worker in workers:
                try:
                    results[label] = (
                        worker.demo() if args.command == "demo" else worker.update(full=args.full)
                    )
                except RadarError as error:
                    failures[label] = str(error)
            if failures:
                print(
                    json.dumps(
                        {
                            "status": "PARTIAL" if results else "ERROR",
                            "completed": results,
                            "errors": failures,
                        },
                        ensure_ascii=False,
                    )
                )
                return 2
            result = results.get("national", results.get("groups"))
            if args.dataset == "all":
                result = {**result, "groups": results["groups"]}
        elif args.command == "status":
            snapshot = repository.snapshot(include_groups=True)
            rows = snapshot["rows"]
            result = {
                "groups_rows": len(snapshot["groups"]),
                "rows": len(rows),
                "from": rows[0]["period"] if rows else None,
                "to": rows[-1]["period"] if rows else None,
                "modes": sorted({row["mode"] for row in rows}),
                "last_run": snapshot["history"][0] if snapshot["history"] else None,
            }
        else:
            with repository.locked() as db:
                rows = (
                    repository.group_rows(db, args.start, args.end)
                    if args.dataset == "groups"
                    else repository.rows(db, args.start, args.end)
                )
            if args.dataset == "groups" and rows:
                rows = filter_group_rows(
                    rows,
                    args.groups,
                    args.start or rows[0]["period"],
                    args.end or rows[-1]["period"],
                )
            if not rows:
                raise RadarError("Nenhum mês encontrado para exportar.")
            data = group_csv_bytes(rows) if args.dataset == "groups" else csv_bytes(rows)
            try:
                publish_csv(args.output, data)
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
