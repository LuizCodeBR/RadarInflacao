"""Painel local: leitura de dados persistidos, sem coleta automática."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from radar_inflacao import __version__
from radar_inflacao.analysis import (
    ESTIMATED_LABEL,
    INDICATORS,
    compare_periods,
    format_points,
    format_rate,
    reference_period,
)
from radar_inflacao.area_pipeline import AreaPipeline
from radar_inflacao.area_view import render_areas
from radar_inflacao.cli import components, project_root
from radar_inflacao.errors import RadarError
from radar_inflacao.group_view import render_groups
from radar_inflacao.index_view import render_indices
from radar_inflacao.inpc import InpcPipeline
from radar_inflacao.model import BASE_MONTH, next_month
from radar_inflacao.pipeline import GroupPipeline
from radar_inflacao.quality_view import render_quality
from radar_inflacao.report import comparison_csv_bytes, csv_bytes

st.set_page_config(page_title="Radar da Inflação", page_icon="📊", layout="wide")
st.title("Radar da Inflação")
st.caption("IPCA e INPC · Dados oficiais do IBGE · Python + SQL")
st.markdown(
    "Explore a evolução dos preços no Brasil com uma base local verificável. "
    "A coleta acontece somente quando você solicita."
)

view = st.radio(
    "Análise",
    [
        "Índice geral",
        "Grupos de despesas",
        "Comparar áreas",
        "IPCA × INPC",
        "Qualidade e atualização",
    ],
    horizontal=True,
    key="view",
)
try:
    repository, pipeline = components()
    group_pipeline = GroupPipeline(repository, project_root() / "sample/groups")
    area_pipeline = AreaPipeline(repository, project_root() / "sample/areas")
    inpc_pipeline = InpcPipeline(repository, project_root() / "sample/inpc")
    if view == "IPCA × INPC":
        inpc_pipeline.ensure_demo()
    if view == "Comparar áreas":
        area_pipeline.ensure_demo()
    pipeline.ensure_demo()
    group_pipeline.ensure_demo()
    snapshot = repository.snapshot(
        include_groups=True,
        include_areas=view == "Comparar áreas",
        include_indices=view == "IPCA × INPC",
    )
except RadarError as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    st.header("Dados e atualização")
    st.markdown("**Fonte:** IBGE / SIDRA · tabelas 1737, 1736 e 7060 · Brasil")
    st.link_button("Consultar a fonte", "https://sidra.ibge.gov.br/tabela/1737")
    st.caption("Atualização padrão: revisita 24 meses e busca meses novos.")
    full = st.checkbox("Reconferir toda a série desde 2020", key="full_refresh")
    simulation_active = view == "Qualidade e atualização" and st.session_state.get(
        "quality_demo", False
    )
    if simulation_active:
        st.info("Desative a demonstração para atualizar sua base principal.")
    if st.button("Atualizar pelo IBGE", type="primary", key="update", disabled=simulation_active):
        completed, errors = [], []
        with st.spinner("Consultando e validando o IBGE…"):
            for label, worker in [
                ("Índice geral", pipeline),
                ("Grupos", group_pipeline),
                ("Áreas", area_pipeline),
                ("INPC", inpc_pipeline),
            ]:
                try:
                    result = worker.update(full=full)
                    completed.append(
                        f"{label}: {result['inserted']} novos, {result['updated']} corrigidos, "
                        f"{result['unchanged']} sem alteração."
                    )
                except RadarError as error:
                    errors.append(f"{label}: {error}")
        st.session_state["notice"] = " ".join(completed)
        st.session_state["update_errors"] = errors
        st.rerun()
    st.divider()
    st.caption("Uso local, sem conta e sem serviço pago. Não há atualização agendada.")

if notice := st.session_state.pop("notice", None):
    st.success(notice)

for error in st.session_state.pop("update_errors", []):
    st.error(error)
    st.info("A última base válida desse conjunto continua disponível.")
if view == "Qualidade e atualização":
    render_quality(repository, project_root())
    st.caption(f"Radar da Inflação {__version__} · Central local, sem consulta automática.")
    st.stop()
if view == "IPCA × INPC":
    render_indices(snapshot["indices"])
    st.caption(f"Radar da Inflação {__version__} · Comparação nacional, com fontes separadas.")
    st.stop()
if view == "Comparar áreas":
    render_areas(snapshot["areas"], snapshot["areas_history"])
    st.caption(
        f"Radar da Inflação {__version__} · Áreas pesquisadas, sem cobertura de todo estado."
    )
    st.stop()
if view == "Grupos de despesas":
    render_groups(snapshot["groups"], snapshot["groups_history"])
    st.caption(f"Radar da Inflação {__version__} · Dados nacionais, sem inflação pessoal.")
    st.stop()

rows = snapshot["rows"]
if not rows:
    st.warning("Não há dados válidos para consultar.")
    st.stop()

modes = {row["mode"] for row in rows}
if modes == {"sample"}:
    st.info(
        "AMOSTRA INCLUÍDA · Dados reais do IBGE obtidos na data de coleta indicada. "
        "Este painel não está consultando a internet automaticamente."
    )
elif modes == {"live"}:
    st.success("BASE CONSULTADA · Dados obtidos pelo comando de atualização do IBGE.")
else:
    st.info(
        "BASE MISTA · Parte da série vem da amostra incluída e parte de consultas posteriores. "
        "Confira a origem de cada mês na tabela ou no CSV."
    )

available = [row["period"] for row in rows]
st.caption(f"Cobertura da base: {available[0]} a {available[-1]} · {len(rows)} meses.")
left, right = st.columns(2)
with left:
    start = st.selectbox("Mês inicial", available, index=max(0, len(available) - 24), key="start")
with right:
    end = st.selectbox("Mês final", available, index=len(available) - 1, key="end")
if start > end:
    st.error("O mês inicial precisa ser anterior ou igual ao final.")
    st.stop()
filtered = [row for row in rows if start <= row["period"] <= end]
st.caption(f"Período aplicado: {start} a {end} · {len(filtered)} meses.")
last = filtered[-1]
st.subheader(f"Indicadores de {last['period']}")
metrics = st.columns(3)
for column, (label, key, explanation) in zip(metrics, INDICATORS, strict=True):
    column.metric(label, format_rate(last[key]), help=explanation)
st.caption(
    "Os três valores acima são os divulgados pelo IBGE para o último mês selecionado. "
    "O filtro não redefine as janelas dos acumulados oficiais."
)

with st.expander("Entenda os indicadores e os cálculos"):
    st.markdown(
        f"**Variação mensal:** compara o nível de preços de {end} com o mês anterior. "
        "Uma taxa negativa indica deflação naquele mês.\n\n"
        f"**Acumulado no ano:** começa em {end[:4]}-01 e termina em {end}, "
        "mesmo que o filtro comece depois de janeiro.\n\n"
        f"**Acumulado em 12 meses:** cobre {next_month(end, -11)} a {end}, "
        "incluindo meses anteriores ao filtro ou à cobertura local, quando necessário. "
        "O valor é fornecido pelo IBGE.\n\n"
        f"**{ESTIMATED_LABEL}:** combina apenas as taxas mensais do intervalo escolhido, "
        "incluindo o primeiro e o último mês. A fórmula é "
        "`[(1 + taxa₁/100) × … × (1 + taxaₙ/100) − 1] × 100`. "
        "Por exemplo, dois meses de 1% resultam em 2,01%, e não 2%. "
        "É uma estimativa a partir das taxas publicadas, que já têm arredondamento; "
        "pode diferir do acumulado oficial calculado com números-índice.\n\n"
        "**Pontos percentuais (p.p.):** diferença entre duas taxas. "
        "Se A for 3% e B for 2%, A − B é +1,00 p.p.\n\n"
        "Uma inflação positiva menor indica preços subindo mais devagar; "
        "não significa, por si só, queda do nível de preços."
    )
    st.markdown(
        "[Inflação e metodologia do IPCA — IBGE](https://www.ibge.gov.br/explica/inflacao.php) · "
        "[Composição dos índices — Banco Central]"
        "(https://www4.bcb.gov.br/pec/correcao/metodologiaInd.asp?frame=1)"
    )

st.caption("O download usa os dados desta tela. Atualize a página para incorporar novas coletas.")
st.subheader("Comparar períodos")
st.caption(f"Período A: {start} a {end} · {len(filtered)} meses · definido pelos filtros acima.")
comparison_labels = {
    "previous": "Período anterior de mesma duração",
    "year": "Mesmo período do ano anterior",
    "custom": "Escolher outro período",
}
mode = st.selectbox(
    "Comparar com",
    list(comparison_labels),
    format_func=comparison_labels.get,
    key="comparison_mode",
)
if mode == "custom":
    default_start, default_end = reference_period(start, end, "previous")
    if default_start not in available or default_end not in available:
        default_start, default_end = start, end
    left_b, right_b = st.columns(2)
    with left_b:
        start_b = st.selectbox(
            "Mês inicial do período B",
            available,
            index=available.index(default_start),
            key="compare_start",
        )
    with right_b:
        end_b = st.selectbox(
            "Mês final do período B",
            available,
            index=available.index(default_end),
            key="compare_end",
        )
else:
    start_b, end_b = reference_period(start, end, mode)
try:
    comparison = compare_periods(rows, start, end, start_b, end_b)
except RadarError as error:
    if mode == "custom":
        st.error(f"Comparação indisponível: {error}")
    else:
        st.info(
            f"Comparação indisponível: {error} "
            "Escolha outro período ou ajuste os filtros. Os dados do período A continuam abaixo."
        )
else:
    st.caption(
        f"Comparação aplicada: A {start} a {end} · B {start_b} a {end_b} · "
        f"{comparison.a.count} e {comparison.b.count} meses."
    )
    if not comparison.same_length:
        st.warning(
            "Os períodos têm durações diferentes. O acumulado não foi anualizado; "
            "considere a quantidade de meses ao interpretar a diferença."
        )
    if comparison.overlap:
        st.info("Os períodos se sobrepõem: alguns meses participam dos dois intervalos.")
    if start == start_b and end == end_b:
        st.info("Os períodos são idênticos; as diferenças são zero.")
    metric_a, metric_b, metric_difference = st.columns(3)
    metric_a.metric("Estimativa do período A", format_rate(comparison.a.compounded))
    metric_b.metric("Estimativa do período B", format_rate(comparison.b.compounded))
    metric_difference.metric(
        "Diferença A − B",
        format_points(comparison.measures[0].difference),
        help="Diferença em pontos percentuais, calculada antes do arredondamento.",
    )
    st.caption(
        "Acumulado estimado pela composição das taxas mensais publicadas. "
        "Não é um novo acumulado oficial do IBGE."
    )
    comparison_table = [
        {
            "Indicador": measure.label,
            "Período A (%)": format_rate(measure.a),
            "Período B (%)": format_rate(measure.b),
            "Diferença A − B (p.p.)": format_points(measure.difference),
        }
        for measure in comparison.measures
    ]
    st.dataframe(comparison_table, hide_index=True, width="stretch", key="comparison_table")
    st.caption(
        "As três linhas oficiais usam o último mês de cada período; suas janelas continuam "
        "sendo mês, ano civil e 12 meses. Diferenças são A − B, antes do arredondamento; "
        "a tela mostra duas casas. Consulte a tabela no computador ou role-a no celular."
    )
    st.download_button(
        "Baixar CSV da comparação",
        comparison_csv_bytes(comparison),
        file_name=f"comparacao-{start}-{end}-vs-{start_b}-{end_b}.csv",
        mime="text/csv",
        key="comparison_csv",
        on_click="ignore",
    )

chart = pd.DataFrame(
    [
        {
            "Mês": row["period"],
            "IPCA mensal (%)": float(row["monthly"]),
            "IPCA em 12 meses (%)": float(row["twelve_month"]),
        }
        for row in filtered
    ]
).set_index("Mês")
st.subheader("Evolução no período A")
st.line_chart(chart, x_label="Mês", y_label="Variação (%)")
st.caption("Taxa mensal e acumulado em 12 meses têm janelas diferentes de medição.")
try:
    monthly_csv = csv_bytes(filtered)
except RadarError as error:
    st.error(f"Exportação indisponível: {error}")
else:
    st.download_button(
        "Baixar CSV do período",
        monthly_csv,
        file_name=f"radar-inflacao-{start}-a-{end}.csv",
        mime="text/csv",
        key="csv",
        on_click="ignore",
    )

with st.expander("Tabela, origem e qualidade", expanded=True):
    table = [
        {
            "Mês": row["period"],
            "Mensal (%)": float(row["monthly"]),
            "No ano (%)": float(row["year_to_date"]),
            "12 meses (%)": float(row["twelve_month"]),
            "Origem do mês": "Amostra incluída" if row["mode"] == "sample" else "Consulta IBGE",
            "Coletado em": row["retrieved_at"],
            "SHA-256 da resposta": row["raw_sha256"],
            "Coleta ID": row["run_id"],
        }
        for row in filtered
    ]
    st.dataframe(table, hide_index=True, width="stretch", key="source_table")
    st.caption(
        "Meses únicos, intervalo contínuo, Brasil, unidade % e três medidas obrigatórias. "
        "Valor ausente nunca é convertido automaticamente em zero."
    )

with st.expander("Histórico das últimas 20 execuções"):
    history = [
        {
            "Coleta": row[0],
            "Início UTC": row[1],
            "Fim UTC": row[2],
            "Modo": row[3],
            "Situação": row[4],
            "Novos": row[5],
            "Corrigidos": row[6],
            "Sem alteração": row[7],
            "Detalhe": row[8],
        }
        for row in snapshot["history"]
    ]
    st.dataframe(history, hide_index=True, width="stretch", key="history_table")
st.divider()
st.caption(
    f"Radar da Inflação {__version__} · Série desde {BASE_MONTH}. "
    "Indicador estatístico nacional; não representa a inflação individual de cada pessoa."
)
