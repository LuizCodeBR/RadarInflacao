import copy
import json
import subprocess
import sys
from decimal import Decimal

import pytest
from conftest import ROOT

from radar_inflacao.errors import BusyError, RadarError, SourceError, ValidationError
from radar_inflacao.model import periods
from radar_inflacao.pipeline import Pipeline
from radar_inflacao.source import METADATA_URL, Download, data_url


class Source:
    def __init__(self, payload, metadata, *, broken=False, changed=False):
        self.payload, self.meta = payload, metadata
        self.broken, self.changed, self.requested = broken, changed, None

    def metadata(self):
        if self.broken:
            raise SourceError("Falha simulada na origem")
        return Download(self.meta, METADATA_URL)

    def observations(self, start, end):
        self.requested = (start, end)
        payload = copy.deepcopy(self.payload)
        keys = {m.replace("-", "") for m in periods(start, end)}
        for variable in payload:
            series = variable["resultados"][0]["series"][0]["serie"]
            variable["resultados"][0]["series"][0]["serie"] = {
                key: value for key, value in series.items() if key in keys
            }
        if self.changed:
            payload[0]["resultados"][0]["series"][0]["serie"]["202610"] = "9.99"
        return Download(json.dumps(payload).encode(), data_url(start, end))


def test_import_is_idempotent_and_archived(pipeline, repository):
    first, second = pipeline.demo(), pipeline.demo()
    assert first["inserted"] == 82
    assert second["inserted"] == second["updated"] == 0
    assert second["unchanged"] == 82
    snapshot = repository.snapshot()
    assert len(snapshot["rows"]) == 82
    assert len(snapshot["history"]) == 2
    assert all(row[4] == "SUCCESS" for row in snapshot["history"])
    assert len(list((repository.directory / "raw").glob("*"))) == 2


def test_failed_download_preserves_previous_base_and_is_recorded(
    pipeline, repository, sample_payload, metadata
):
    pipeline.demo()
    before = repository.snapshot()["rows"]
    broken = Pipeline(repository, ROOT / "sample", Source(sample_payload, metadata, broken=True))
    with pytest.raises(SourceError):
        broken.update()
    after = repository.snapshot()
    assert after["rows"] == before
    assert after["history"][0][4] == "FAILED"


def test_incremental_update_revisits_24_months_and_tracks_revisions(
    pipeline, repository, sample_payload, metadata
):
    pipeline.demo()
    source = Source(sample_payload, metadata, changed=True)
    result = Pipeline(repository, ROOT / "sample", source).update()
    assert source.requested == ("2024-11", "2026-10")
    assert result["updated"] == 1
    assert result["inserted"] == 0
    rows = repository.snapshot()["rows"]
    assert len(rows) == 82
    assert rows[-1]["monthly"] == Decimal("9.99")
    assert rows[-1]["mode"] == "live"
    assert rows[0]["mode"] == "sample"
    with pytest.raises(ValidationError, match="não substitui"):
        pipeline.demo()


def test_full_update_reconciles_all_rows(pipeline, repository, sample_payload, metadata):
    pipeline.demo()
    source = Source(sample_payload, metadata)
    result = Pipeline(repository, ROOT / "sample", source).update(full=True)
    assert result["unchanged"] == 82
    assert source.requested == ("2020-01", "2026-10")
    assert {row["mode"] for row in repository.snapshot()["rows"]} == {"live"}


def test_partial_transaction_failure_rolls_back(pipeline, repository, monkeypatch):
    pipeline.demo()
    before = repository.snapshot()["rows"]
    original = repository.upsert

    def failing(db, rows, run_id):
        original(db, rows[:1], run_id)
        raise RuntimeError("simulated failure before commit")

    monkeypatch.setattr(repository, "upsert", failing)
    with pytest.raises(RadarError, match="preservada"):
        pipeline.demo()
    snapshot = repository.snapshot()
    assert snapshot["rows"] == before
    assert snapshot["history"][0][4] == "FAILED"


def test_changed_sample_hash_is_rejected_before_publish(pipeline, repository, tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    for name in ("ibge-1737.json", "metadata-1737.json", "manifest.json"):
        (sample / name).write_bytes((ROOT / "sample" / name).read_bytes())
    (sample / "ibge-1737.json").write_text("[]")
    with pytest.raises(ValidationError, match="integridade"):
        Pipeline(repository, sample).demo()
    assert repository.snapshot()["rows"] == []


def test_database_lock_excludes_a_second_process(repository, pipeline):
    script = (
        "from filelock import FileLock; import sys; "
        f"lock=FileLock({str(repository.lock_path)!r}); lock.acquire(); "
        "print('LOCKED',flush=True); sys.stdin.readline(); lock.release()"
    )
    with subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout.readline().strip() == "LOCKED"
            with pytest.raises(BusyError):
                pipeline.demo()
        finally:
            process.communicate("\n", timeout=10)
    assert pipeline.demo()["inserted"] == 82


def test_interrupted_run_becomes_explicit(repository):
    with repository.locked() as db:
        db.execute("INSERT INTO ingestion(id,status) VALUES('interrupted','RUNNING')")
    assert repository.snapshot()["history"][0][4] == "INTERRUPTED"


def test_unexpected_schema_is_not_overwritten(repository):
    with repository.locked() as db:
        db.execute("UPDATE schema_version SET version=99")
    with pytest.raises(ValidationError, match="incompatível"):
        repository.snapshot()
