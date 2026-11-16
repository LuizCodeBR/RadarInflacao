import json
from pathlib import Path

import pytest

from radar_inflacao.pipeline import Pipeline
from radar_inflacao.storage import Repository

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "data")


@pytest.fixture
def pipeline(repository):
    return Pipeline(repository, ROOT / "sample")


@pytest.fixture
def sample_payload():
    return json.loads((ROOT / "sample/ibge-1737.json").read_bytes())


@pytest.fixture
def metadata():
    return (ROOT / "sample/metadata-1737.json").read_bytes()
