from conftest import ROOT
from streamlit.testing.v1 import AppTest


def start_app(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DATA_DIR", str(tmp_path / "data"))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()


def frame_with(app, column):
    return next(frame.value for frame in app.dataframe if column in frame.value.columns)


def test_offline_dashboard_loads_sample_and_filters(tmp_path, monkeypatch):
    app = start_app(tmp_path, monkeypatch)
    assert not app.exception
    assert any("AMOSTRA INCLUÍDA" in info.value for info in app.info)
    assert len(app.metric) == 6
    app.selectbox(key="start").select("2024-01")
    app.selectbox(key="end").select("2024-03")
    app.run()
    assert not app.exception
    assert [metric.value for metric in app.metric[:3]] == ["0,16%", "1,42%", "3,93%"]
    assert app.metric[3].value == "1,42%"
    assert any("B 2023-10 a 2023-12" in item.value for item in app.caption)
    app.selectbox(key="start").select("2024-04").run()
    assert any("inicial" in error.value for error in app.error)
    assert not app.metric


def test_dashboard_source_failure_keeps_sample(tmp_path, monkeypatch):
    from radar_inflacao.errors import SourceError
    from radar_inflacao.source import IbgeSource

    app = start_app(tmp_path, monkeypatch)

    def fail(_):
        raise SourceError("IBGE temporariamente indisponível")

    monkeypatch.setattr(IbgeSource, "metadata", fail)
    app.button(key="update").click().run()
    assert not app.exception
    assert any("indisponível" in error.value for error in app.error)
    assert frame_with(app, "Situação")["Situação"].iloc[0] == "FAILED"
    assert any("AMOSTRA INCLUÍDA" in info.value for info in app.info)
    assert len(app.metric) == 6


def test_previous_year_comparison_and_contextual_explanations(tmp_path, monkeypatch):
    app = start_app(tmp_path, monkeypatch)
    app.selectbox(key="start").select("2024-02")
    app.selectbox(key="end").select("2024-03")
    app.selectbox(key="comparison_mode").select("year")
    app.run()
    assert not app.exception
    assert any("B 2023-02 a 2023-03" in item.value for item in app.caption)
    text = "\n".join(item.value for item in app.markdown)
    assert "2024-01" in text  # O acumulado oficial começa antes do filtro.
    assert "2023-04 a 2024-03" in text
    assert "arredondamento" in text and "Pontos percentuais" in text
    table = frame_with(app, "Indicador")
    assert table.iloc[0]["Indicador"] == "Acumulado estimado no período"
    assert table.iloc[1]["Período A (%)"] == "0,16%"


def test_missing_reference_keeps_main_view_without_truncating(tmp_path, monkeypatch):
    app = start_app(tmp_path, monkeypatch)
    app.selectbox(key="start").select("2020-01")
    app.selectbox(key="end").select("2020-03")
    app.run()
    assert not app.exception
    assert len(app.metric) == 3
    assert any("cobertura completa" in item.value for item in app.info)
    assert len(frame_with(app, "Origem do mês")) == 3
    assert not app.error


def test_custom_periods_warn_about_lengths_overlap_and_identical_ranges(tmp_path, monkeypatch):
    app = start_app(tmp_path, monkeypatch)
    app.selectbox(key="start").select("2024-01")
    app.selectbox(key="end").select("2024-03")
    app.selectbox(key="comparison_mode").select("custom")
    app.run()
    app.selectbox(key="compare_start").select("2024-02")
    app.selectbox(key="compare_end").select("2024-03")
    app.run()
    assert not app.exception
    assert any("durações diferentes" in item.value for item in app.warning)
    assert any("sobrepõem" in item.value for item in app.info)
    app.selectbox(key="compare_start").select("2024-01").run()
    assert any("idênticos" in item.value for item in app.info)
    assert app.metric[5].value == "0,00 p.p."
    app.selectbox(key="compare_start").select("2024-04").run()
    assert any("Comparação indisponível" in item.value for item in app.error)
    assert len(app.metric) == 3
    assert len(frame_with(app, "Origem do mês")) == 3


def test_changing_comparison_neither_collects_nor_writes_data(tmp_path, monkeypatch):
    from radar_inflacao.source import IbgeSource
    from radar_inflacao.storage import Repository

    app = start_app(tmp_path, monkeypatch)
    repository = Repository(tmp_path / "data")
    before = repository.snapshot()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("Filtros não devem chamar o IBGE.")

    monkeypatch.setattr(IbgeSource, "metadata", unexpected)
    monkeypatch.setattr(IbgeSource, "observations", unexpected, raising=False)
    app.selectbox(key="comparison_mode").select("year").run()
    app.selectbox(key="comparison_mode").select("custom").run()
    assert not app.exception
    assert repository.snapshot() == before
