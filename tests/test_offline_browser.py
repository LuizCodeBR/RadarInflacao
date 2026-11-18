"""Integração opcional com navegador instalado; a distribuição não contém Playwright."""

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ROOT

from radar_inflacao.analysis import format_points, format_rate
from radar_inflacao.index_report import index_csv_bytes
from radar_inflacao.indices import MEASURES, index_pairs
from radar_inflacao.offline import load_sample_indices, render_html


def prepare_browser_case(folder):
    indices = load_sample_indices(ROOT / "sample")
    destination = folder / "Pasta com espaços" / "ABRIR-DEMONSTRACAO.html"
    destination.parent.mkdir(parents=True)
    destination.write_text(render_html(indices), encoding="utf-8")
    cases = []
    for start, end, filename in [
        ("2025-11", "2026-10", "twelve.csv"),
        ("2020-01", "2026-10", "full.csv"),
        ("2024-01", "2024-03", "quarter.csv"),
        ("2026-10", "2026-10", "single.csv"),
    ]:
        pairs = index_pairs(indices, start, end)
        expected = {
            measure: [
                [
                    format_rate(pair["ipca"][measure]).removesuffix("%"),
                    format_rate(pair["inpc"][measure]).removesuffix("%"),
                    format_points(pair["differences"][measure]).removesuffix(" p.p."),
                ]
                for pair in pairs
            ]
            for measure in MEASURES
        }
        cases.append(
            {"start": start, "end": end, "count": len(pairs), "measures": expected, "csv": filename}
        )
        (folder / filename).write_bytes(index_csv_bytes(indices, start, end))
    (folder / "expected.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    zero = {key: copy.deepcopy(rows[-1:]) for key, rows in indices.items()}
    zero["inpc"][0]["year_to_date"] = zero["ipca"][0]["year_to_date"]
    (folder / "zero.html").write_text(render_html(zero), encoding="utf-8")
    (folder / "zero.csv").write_bytes(index_csv_bytes(zero, "2026-10", "2026-10"))


def test_browser_offline_filters_charts_downloads_and_mobile(tmp_path):
    module = os.environ.get("RADAR_PLAYWRIGHT_MODULE")
    node = shutil.which("node")
    if not module or not Path(module).exists() or not node:
        if os.environ.get("RADAR_REQUIRE_BROWSER") == "1":
            pytest.fail("Informe RADAR_PLAYWRIGHT_MODULE e disponibilize Node para o teste real.")
        pytest.skip("Teste real disponível com Node e RADAR_PLAYWRIGHT_MODULE configurados.")
    prepare_browser_case(tmp_path)
    env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path), TMPDIR=str(tmp_path))
    result = subprocess.run(
        [node, str(ROOT / "tests/browser_offline.cjs"), str(tmp_path)],
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "browser-result.json").read_text())
    assert report["passed"] and report["downloads"] == 9
    assert report["networkRequests"] == 0 and report["javascriptErrors"] == 0
