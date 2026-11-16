from conftest import ROOT
from streamlit.testing.v1 import AppTest


def test_offline_dashboard_loads_sample_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any("AMOSTRA INCLUÍDA" in info.value for info in app.info)
    assert len(app.metric) == 3
    app.selectbox(key="start").select("2024-01")
    app.selectbox(key="end").select("2024-03")
    app.run()
    assert not app.exception
    assert app.metric[0].value == "0,16%"
    assert app.metric[1].value == "1,42%"
    assert app.metric[2].value == "3,93%"
    app.selectbox(key="start").select("2024-04").run()
    assert any("inicial" in error.value for error in app.error)
    assert not app.metric


def test_dashboard_source_failure_keeps_sample(tmp_path, monkeypatch):
    from radar_inflacao.errors import SourceError
    from radar_inflacao.source import IbgeSource

    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()

    def fail(_):
        raise SourceError("IBGE temporariamente indisponível")

    monkeypatch.setattr(IbgeSource, "metadata", fail)
    app.button(key="update").click().run()
    assert not app.exception
    assert any("indisponível" in error.value for error in app.error)
    assert app.dataframe[1].value["Situação"].iloc[0] == "FAILED"
    assert any("AMOSTRA INCLUÍDA" in info.value for info in app.info)
    assert len(app.metric) == 3
