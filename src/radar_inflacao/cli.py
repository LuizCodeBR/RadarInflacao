"""python -m radar_inflacao: demo, update, status e export."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .area_pipeline import AreaPipeline
from .area_report import area_csv_bytes
from .areas import AREAS, LOCATIONS
from .errors import RadarError, ValidationError
from .groups import GROUPS, filter_group_rows
from .index_report import index_comparison_csv_bytes, index_csv_bytes, inpc_csv_bytes
from .indices import index_comparisons
from .inpc import InpcPipeline
from .model import month, periods
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
        description="Radar da Inflação — dados oficiais do IPCA e INPC nacionais"
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Pasta independente para banco, brutos e histórico"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Importa as amostras locais validadas, sem internet")
    demo.add_argument(
        "--dataset", choices=["all", "national", "groups", "areas", "inpc"], default="all"
    )
    update = sub.add_parser("update", help="Consulta o IBGE sob demanda")
    update.add_argument(
        "--dataset", choices=["all", "national", "groups", "areas", "inpc"], default="all"
    )
    update.add_argument(
        "--full", action="store_true", help="Reconcilia desde 2020, incluindo revisões antigas"
    )
    sub.add_parser("quality", help="Mostra o relatório local de qualidade, sem consultar a rede")
    sub.add_parser("quality-demo", help="Cria demonstração offline em .cache/quality-demo")
    quality_export = sub.add_parser("quality-export", help="Exporta qualidade ou mudanças em CSV")
    quality_export.add_argument("--report", choices=["summary", "changes"], default="summary")
    quality_export.add_argument(
        "--dataset", choices=["all", "national", "groups", "areas", "inpc"], default="all"
    )
    quality_export.add_argument("--kind", choices=["all", "ADDED", "CHANGED"], default="CHANGED")
    quality_export.add_argument("--group", choices=list(GROUPS))
    quality_export.add_argument("--area", choices=list(LOCATIONS))
    quality_export.add_argument("--from", dest="start", type=month_argument)
    quality_export.add_argument("--to", dest="end", type=month_argument)
    quality_export.add_argument("--output", type=Path, required=True)
    sub.add_parser("status", help="Mostra cobertura e última execução")
    export = sub.add_parser("export", help="Exporta a base sem substituir arquivo existente")
    export.add_argument(
        "--dataset", choices=["national", "groups", "areas", "inpc", "indices"], default="national"
    )
    export.add_argument("--groups", nargs="+", choices=list(GROUPS), default=list(GROUPS))
    export.add_argument("--areas", nargs="+", choices=list(AREAS), default=list(AREAS))
    export.add_argument("--from", dest="start", type=month_argument)
    export.add_argument("--to", dest="end", type=month_argument)
    export.add_argument("--output", type=Path, required=True)
    comparison = sub.add_parser("compare-indices", help="Exporta a comparação A/B IPCA × INPC")
    comparison.add_argument("--from", dest="start", type=month_argument, required=True)
    comparison.add_argument("--to", dest="end", type=month_argument, required=True)
    comparison.add_argument("--from-b", dest="bs", type=month_argument, required=True)
    comparison.add_argument("--to-b", dest="be", type=month_argument, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    html_demo = sub.add_parser("demo-html", help="Gera HTML offline sem Python no destino")
    html_demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo-html":
            if args.data_dir is not None:
                raise RadarError("O HTML usa somente as amostras incluídas; omita --data-dir.")
            from .offline import write_demo

            result = write_demo(project_root() / "sample", args.output)
            print(json.dumps(result, ensure_ascii=False))
            return 0
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
            allow_simulation=args.command
            in ("quality", "quality-export", "status", "export", "compare-indices"),
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
                    "area_key": args.area,
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
            area_pipeline = AreaPipeline(repository, project_root() / "sample/areas")
            all_workers = {
                "national": pipeline,
                "groups": group_pipeline,
                "areas": area_pipeline,
                "inpc": InpcPipeline(repository, project_root() / "sample/inpc"),
            }
            workers = (
                list(all_workers.items())
                if args.dataset == "all"
                else [(args.dataset, all_workers[args.dataset])]
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
            result = next(iter(results.values()))
            if args.dataset == "all":
                result = {
                    **result,
                    "groups": results["groups"],
                    "areas": results["areas"],
                    "inpc": results["inpc"],
                }
        elif args.command == "status":
            snapshot = repository.snapshot(
                include_groups=True, include_areas=True, include_indices=True
            )
            rows = snapshot["rows"]
            result = {
                "inpc_rows": len(snapshot["indices"]["inpc"]),
                "areas_rows": len(snapshot["areas"]),
                "groups_rows": len(snapshot["groups"]),
                "rows": len(rows),
                "from": rows[0]["period"] if rows else None,
                "to": rows[-1]["period"] if rows else None,
                "modes": sorted({row["mode"] for row in rows}),
                "last_run": snapshot["history"][0] if snapshot["history"] else None,
            }
        elif args.command == "compare-indices" or (
            args.command == "export" and args.dataset in ("indices", "inpc")
        ):
            from .index_storage import index_rows

            with repository.locked() as db:
                indices = {key: index_rows(db, key) for key in ("ipca", "inpc")}
            if args.command == "compare-indices":
                data = index_comparison_csv_bytes(
                    index_comparisons(indices, args.start, args.end, args.bs, args.be)
                )
                count = 4
            else:
                rows = (
                    indices["inpc"]
                    if args.dataset == "inpc"
                    else [row for series in indices.values() for row in series]
                )
                if not rows:
                    raise RadarError("Nenhum mês encontrado para exportar.")
                start = args.start or min(r["period"] for r in rows)
                end = args.end or max(r["period"] for r in rows)
                if args.dataset == "indices":
                    data = index_csv_bytes(indices, start, end)
                else:
                    data = inpc_csv_bytes(indices["inpc"], start, end)
                count = len(periods(start, end))
            try:
                publish_csv(args.output, data)
            except FileExistsError as exc:
                raise RadarError("O arquivo já existe. Escolha outro destino.") from exc
            result = {"exported": count, "file": str(args.output.resolve())}
        else:
            with repository.locked() as db:
                rows = (
                    repository.area_rows(db)
                    if args.dataset == "areas"
                    else repository.group_rows(db, args.start, args.end)
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
            data = (
                area_csv_bytes(
                    rows,
                    args.areas,
                    args.start or rows[0]["period"],
                    args.end or rows[-1]["period"],
                )
                if args.dataset == "areas"
                else group_csv_bytes(rows)
                if args.dataset == "groups"
                else csv_bytes(rows)
            )
            try:
                publish_csv(args.output, data)
            except FileExistsError as exc:
                raise RadarError("O arquivo já existe. Escolha outro destino.") from exc
            count = (
                len(args.areas)
                * len(periods(args.start or rows[0]["period"], args.end or rows[-1]["period"]))
                if args.dataset == "areas"
                else len(rows)
            )
            result = {"exported": count, "file": str(args.output.resolve())}
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    except (RadarError, OSError) as exc:
        print(json.dumps({"status": "ERROR", "detail": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
