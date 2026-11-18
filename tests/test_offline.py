"""Contrato do HTML offline: fontes, cobertura, precisão, CSV e geração isolada."""

import copy
import hashlib
import json
import re
import shutil
from decimal import Decimal

import pytest
from conftest import ROOT

from radar_inflacao.cli import main
from radar_inflacao.errors import ValidationError
from radar_inflacao.index_report import index_csv_bytes
from radar_inflacao.offline import load_sample_indices, make_payload, render_html, write_demo


@pytest.fixture(scope="module")
def offline_indices():
    return load_sample_indices(ROOT / "sample")


def test_sample_covers_both_indices_and_independent_sources(offline_indices):
    payload = make_payload(offline_indices)
    assert (payload["start"], payload["end"], len(payload["rows"])) == ("2020-01", "2026-10", 82)
    last = payload["rows"][-1]
    assert last["display"]["ipca"]["monthly"] == "0,14"
    assert last["display"]["inpc"]["monthly"] == "0,22"
    assert last["display"]["difference"]["monthly"] == "+0,08"
    assert last["display"]["difference"]["twelve_month"] == "-0,14"
    assert len(payload["sources"]) == 2
    assert payload["sources"][0]["sample_id"] != payload["sources"][1]["sample_id"]
    for source in payload["sources"]:
        key = source["index"].lower()
        folder = ROOT / "sample" / ("inpc" if key == "inpc" else "")
        manifest = json.loads((folder / "manifest.json").read_text())
        assert source["sha256"] == manifest["sha256"]
        assert source["retrieved_at"] == manifest["retrieved_at"]
        assert source["url"] == manifest["data_url"]


@pytest.mark.parametrize(
    "start,end",
    [
        ("2020-01", "2026-10"),
        ("2025-11", "2026-10"),
        ("2024-01", "2024-03"),
        ("2026-10", "2026-10"),
        ("2020-01", "2020-01"),
    ],
)
def test_embedded_csv_matches_existing_exporter_byte_for_byte(offline_indices, start, end):
    payload = make_payload(offline_indices)
    lines = [r["csv"] for r in payload["rows"] if start <= r["period"] <= end]
    actual = ("\ufeff" + payload["csv_header"] + "".join(lines)).encode("utf-8")
    assert actual == index_csv_bytes(offline_indices, start, end)
    assert actual.startswith(b"\xef\xbb\xbf")


def test_differences_preserve_decimal_precision_and_zero(offline_indices):
    indices = copy.deepcopy(offline_indices)
    for key in indices:
        indices[key] = indices[key][-1:]
    indices["ipca"][0]["monthly"] = Decimal("0.123456")
    indices["inpc"][0]["monthly"] = Decimal("0.123457")
    indices["inpc"][0]["year_to_date"] = indices["ipca"][0]["year_to_date"]
    payload = make_payload(indices)
    assert Decimal(payload["rows"][0]["values"]["difference"]["monthly"]) == Decimal("0.000001")
    assert payload["rows"][0]["display"]["difference"]["year_to_date"] == "0,00"
    assert ";0,000001;" in payload["rows"][0]["csv"]


@pytest.mark.parametrize(
    "change", ["missing_middle", "shorter_coverage", "duplicate", "live", "empty"]
)
def test_refuses_missing_inconsistent_or_personal_data(offline_indices, change):
    indices = copy.deepcopy(offline_indices)
    if change == "missing_middle":
        indices["inpc"].pop(20)
    elif change == "shorter_coverage":
        indices["inpc"].pop()
    elif change == "duplicate":
        indices["inpc"].append(copy.deepcopy(indices["inpc"][0]))
    elif change == "live":
        indices["inpc"][0]["mode"] = "live"
    else:
        indices["inpc"] = []
    with pytest.raises(ValidationError):
        render_html(indices)


@pytest.mark.parametrize("change", ["bytes", "url", "date", "metadata"])
def test_invalid_samples_never_produce_html(tmp_path, change):
    sample = tmp_path / "sample"
    shutil.copytree(ROOT / "sample", sample)
    if change == "bytes":
        (sample / "ibge-1737.json").write_bytes(b"[]")
    elif change == "metadata":
        (sample / "inpc/metadata-1736.json").write_bytes(b"{}")
    else:
        path = sample / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["data_url" if change == "url" else "retrieved_at"] = (
            manifest["data_url"] + "&extra=1" if change == "url" else "2026-11-16"
        )
        path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "invalid.html"
    with pytest.raises(ValidationError):
        write_demo(sample, output)
    assert not output.exists()


def test_html_is_self_contained_and_deterministic(offline_indices, monkeypatch):
    import httpx

    def unexpected(*args, **kwargs):
        pytest.fail("A demonstração não pode consultar a rede.")

    monkeypatch.setattr(httpx.Client, "request", unexpected)
    html = render_html(load_sample_indices(ROOT / "sample"))
    assert html == render_html(offline_indices)
    assert not re.search(r"<(?:script|link|img)[^>]+(?:src|href)\s*=", html)
    assert "connect-src 'none'" in html
    assert "<!--RADAR_DATA-->" not in html and "/* RADAR_SCRIPT */" not in html
    embedded = json.loads(
        re.search(r'<script id="radar-data" type="application/json">(.*?)</script>', html, re.S)[1]
    )
    assert len(embedded["rows"]) == 82
    assert "fetch(" not in html and "localStorage" not in html


def test_script_data_cannot_close_its_element(offline_indices, monkeypatch):
    import radar_inflacao.offline as module

    attack = '</script><img src=x onerror="alert(1)">'
    monkeypatch.setattr(module, "__version__", attack)
    html = render_html(offline_indices)
    assert attack not in html
    embedded = re.search(
        r'<script id="radar-data" type="application/json">(.*?)</script>', html, re.S
    )[1]
    assert json.loads(embedded)["version"] == attack


def test_cli_does_not_open_database_and_never_overwrites(tmp_path, capsys, monkeypatch):
    import radar_inflacao.cli as cli

    monkeypatch.setattr(cli, "components", lambda *a, **k: pytest.fail("Não deve abrir banco"))
    output = tmp_path / "Pasta com espaços" / "ABRIR-DEMONSTRACAO.html"
    args = ["demo-html", "--output", str(output)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["months"] == 82
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert main(args) == 2
    assert "já existe" in capsys.readouterr().out
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
    assert main(["--data-dir", str(tmp_path / "data"), *args]) == 2
    assert "omita --data-dir" in capsys.readouterr().out
    assert not (tmp_path / "data").exists()
    assert main(["demo-html", "--output", str(tmp_path / "bad.csv")]) == 2
    assert ".html" in capsys.readouterr().out
    assert not (tmp_path / "bad.csv").exists()


def test_zip_contains_only_portable_demo_and_matches_generated_html(tmp_path, offline_indices):
    import importlib.util
    from zipfile import ZipFile

    spec = importlib.util.spec_from_file_location("package_demo", ROOT / "scripts/package_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.package_demo(tmp_path / "entrega")
    with ZipFile(result["zip"]) as archive:
        names = archive.namelist()
        assert len(names) == 2
        assert all(not name.startswith("/") and ".." not in name.split("/") for name in names)
        html_name = next(name for name in names if name.endswith(".html"))
        assert archive.read(html_name) == render_html(offline_indices).encode("utf-8")
        assert archive.testzip() is None
    original = (tmp_path / "entrega/ABRIR-DEMONSTRACAO.html").read_bytes()
    with pytest.raises(FileExistsError):
        module.package_demo(tmp_path / "entrega")
    assert (tmp_path / "entrega/ABRIR-DEMONSTRACAO.html").read_bytes() == original
    other = module.package_demo(tmp_path / "outra pasta")
    assert other["sha256"] == result["sha256"]
