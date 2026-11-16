"""Painel local: leitura de dados persistidos, sem coleta automática."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from radar_inflacao.cli import components
from radar_inflacao.errors import RadarError
from radar_inflacao.model import BASE_MONTH
from radar_inflacao.report import csv_bytes

st.set_page_config(page_title="Radar da Inflação", page_icon="📊", layout="wide")
st.title("Radar da Inflação")
st.caption("IPCA nacional · Dados oficiais do IBGE · Python + SQL")
st.markdown(
    "Explore a evolução dos preços no Brasil com uma base local verificável. "
    "A coleta acontece somente quando você solicita."
)

repository, pipeline = components()
try:
    pipeline.ensure_demo()
    snapshot = repository.snapshot()
except RadarError as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    st.header("Dados e atualização")
    st.markdown("**Fonte:** IBGE / SIDRA · tabela 1737 · Brasil")
    st.link_button("Consultar a fonte", "https://sidra.ibge.gov.br/tabela/1737")
    st.caption("Atualização padrão: revisita 24 meses e busca meses novos.")
    full = st.checkbox("Reconferir toda a série desde 2020", key="full_refresh")
    if st.button("Atualizar pelo IBGE", type="primary", key="update"):
        try:
            with st.spinner("Consultando e validando o IBGE…"):
                result = pipeline.update(full=full)
            st.session_state["notice"] = (
                f"Coleta concluída: {result['inserted']} meses novos, "
                f"{result['updated']} corrigidos e {result['unchanged']} sem alteração."
            )
            st.rerun()
        except RadarError as error:
            st.error(str(error))
            st.info("A última base válida continua disponível.")
            try:
                snapshot = repository.snapshot()
            except RadarError:
                pass
    st.divider()
    st.caption("Uso local, sem conta e sem serviço pago. Não há atualização agendada.")

if notice := st.session_state.pop("notice", None):
    st.success(notice)

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
for column, label, key in zip(
    metrics,
    ["Variação mensal", "Acumulado no ano", "Acumulado em 12 meses"],
    ["monthly", "year_to_date", "twelve_month"],
    strict=True,
):
    column.metric(label, f"{last[key]:.2f}%".replace(".", ","))
st.caption(
    "Os três valores acima são os divulgados pelo IBGE para o último mês selecionado. "
    "Acumulado no ano começa em janeiro; acumulado em 12 meses não é a soma das taxas mensais."
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
st.subheader("Evolução no período")
st.line_chart(chart, x_label="Mês", y_label="Variação (%)")
st.caption("Taxa mensal e acumulado em 12 meses têm janelas diferentes de medição.")
st.download_button(
    "Baixar CSV do período",
    csv_bytes(filtered),
    file_name=f"radar-inflacao-{start}-a-{end}.csv",
    mime="text/csv",
    key="csv",
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
    st.dataframe(table, hide_index=True, width="stretch")
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
    st.dataframe(history, hide_index=True, width="stretch")
st.divider()
st.caption(
    f"Radar da Inflação 0.1.0 · Série desde {BASE_MONTH}. "
    "Indicador estatístico nacional; não representa a inflação individual de cada pessoa."
)
