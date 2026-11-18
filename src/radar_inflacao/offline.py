"""Demonstração HTML autossuficiente, gerada somente das amostras verificadas."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from . import __version__
from .analysis import format_points, format_rate
from .errors import ValidationError
from .index_report import index_csv_bytes
from .indices import INDICES, MEASURES, index_pairs
from .inpc import InpcPipeline
from .model import periods
from .pipeline import Pipeline, sample_batch
from .report import publish_csv


def load_sample_indices(sample_directory):
    """Valida bytes, metadados, origem e cobertura sem abrir banco ou acessar a rede.

    O UUID identifica a amostra de forma reprodutível, não uma consulta nova ao IBGE.
    """
    result = {}
    for key, worker in (("ipca", Pipeline), ("inpc", InpcPipeline)):
        folder = sample_directory / "inpc" if key == "inpc" else sample_directory
        batch = sample_batch(folder, worker.source_type.api)
        available = worker.metadata_validator(batch.metadata)
        if batch.end > available or batch.source_url != worker.source_url_builder(
            batch.start, batch.end
        ):
            raise ValidationError("A origem ou cobertura da amostra nacional é incompatível.")
        observations = worker.parser(batch.raw, periods(batch.start, batch.end))
        digest = hashlib.sha256(batch.raw).hexdigest()
        identity = str(uuid5(NAMESPACE_URL, f"radar-sample:{key}:{digest}:{batch.retrieved_at}"))
        result[key] = [
            {
                **asdict(row),
                "mode": "sample",
                "retrieved_at": batch.retrieved_at,
                "raw_sha256": digest,
                "run_id": identity,
                "run_status": "SUCCESS",
                "run_start": batch.start,
                "run_end": batch.end,
                "run_finished_at": batch.retrieved_at,
                "period_day": 1,
                "source_url": batch.source_url,
            }
            for row in observations
        ]
    # A geração exige toda a cobertura dos dois índices, sem interseção silenciosa.
    make_payload(result)
    return result


def make_payload(indices):
    from .indices import validate_indices

    validate_indices(indices)
    if not all(indices.values()):
        raise ValidationError("A demonstração exige amostras dos dois índices.")
    all_rows = [row for rows in indices.values() for row in rows]
    if any(row["mode"] != "sample" for row in all_rows):
        raise ValidationError("A demonstração pública aceita apenas amostras identificadas.")
    start = min(row["period"] for row in all_rows)
    end = max(row["period"] for row in all_rows)
    pairs = index_pairs(indices, start, end)
    # Serialização oficial preparada pelo Python: o navegador só seleciona linhas.
    csv_lines = index_csv_bytes(indices, start, end).decode("utf-8-sig").splitlines(keepends=True)
    if len(csv_lines) != len(pairs) + 1:
        raise ValidationError("CSV da amostra contém uma estrutura inesperada.")
    rows = []
    for pair, csv_line in zip(pairs, csv_lines[1:], strict=True):
        values = {key: pair[key] for key in INDICES} | {"difference": pair["differences"]}
        rows.append(
            {
                "period": pair["period"],
                "values": {
                    key: {field: format(row[field], "f") for field in MEASURES}
                    for key, row in values.items()
                },
                "display": {
                    key: {
                        field: (
                            format_points(row[field]).removesuffix(" p.p.")
                            if key == "difference"
                            else format_rate(row[field]).removesuffix("%")
                        )
                        for field in MEASURES
                    }
                    for key, row in values.items()
                },
                "csv": csv_line,
            }
        )
    sources = []
    for key, label in INDICES.items():
        for row in indices[key]:
            item = {
                "index": label,
                "retrieved_at": row["retrieved_at"],
                "sha256": row["raw_sha256"],
                "sample_id": row["run_id"],
                "url": row["source_url"],
            }
            if item not in sources:
                sources.append(item)
    return {
        "version": __version__,
        "start": start,
        "end": end,
        "measures": MEASURES,
        "rows": rows,
        "sources": sources,
        "csv_header": csv_lines[0],
    }


def render_html(indices):
    payload = json.dumps(make_payload(indices), ensure_ascii=False, separators=(",", ":"))
    # Nunca permite que texto de origem encerre o elemento de dados ou vire HTML.
    payload = payload.replace("&", r"\u0026").replace("<", r"\u003c").replace(">", r"\u003e")
    folder = Path(__file__).parent
    template = (folder / "offline.html").read_text(encoding="utf-8")
    script = (folder / "offline.js").read_text(encoding="utf-8")
    return template.replace("<!--RADAR_DATA-->", payload).replace("/* RADAR_SCRIPT */", script)


def write_demo(sample_directory, output):
    if output.suffix.lower() != ".html":
        raise ValidationError("Escolha um arquivo com extensão .html para a demonstração.")
    indices = load_sample_indices(sample_directory)
    raw = render_html(indices).encode("utf-8")
    try:
        publish_csv(output, raw)
    except FileExistsError as exc:
        raise ValidationError("O arquivo já existe. Escolha outro destino.") from exc
    return {"file": str(output.resolve()), "months": len(indices["ipca"]), "offline": True}
