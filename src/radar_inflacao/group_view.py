"""Interface dos grupos; filtros e downloads usam o mesmo snapshot."""

import math

import altair as alt
import pandas as pd
import streamlit as st

from .analysis import format_points, format_rate, reference_period
from .errors import RadarError
from .groups import (
    GROUPS,
    filter_group_rows,
    group_comparisons,
    group_ranking,
    validate_group_rows,
)
from .report import group_comparison_csv_bytes, group_csv_bytes


def _rate(value):
    return "Não disponível" if value is None else format_rate(value)


def ranking_chart(ranking):
    data = pd.DataFrame(
        {
            "Grupo": [GROUPS[r["group_id"]] for r in ranking],
            "Variação mensal (%)": [float(r["monthly"]) for r in ranking],
        }
    )
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            y=alt.Y("Grupo:N", sort=data["Grupo"].tolist(), axis=alt.Axis(labelLimit=190)),
            x=alt.X("Variação mensal (%):Q"),
            color=alt.condition(
                alt.datum["Variação mensal (%)"] < 0, alt.value("#ce653c"), alt.value("#087e8b")
            ),
            tooltip=["Grupo:N", alt.Tooltip("Variação mensal (%):Q", format=".2f")],
        )
        .properties(height=max(180, len(ranking) * 30))
    )


def evolution_chart(selected, measure):
    records = [
        {
            "Mês": row["period"],
            "Grupo": GROUPS[row["group_id"]],
            "Taxa (%)": None if row[measure] is None else float(row[measure]),
        }
        for row in selected
    ]
    # A aplicação limita a 1200 meses × 9 grupos. Dados inline evitam alterar
    # o limite global do Altair, compartilhado por sessões do mesmo processo.
    return (
        alt.Chart(alt.Data(values=records))
        .mark_line()
        .encode(
            x=alt.X("Mês:O", sort=sorted({r["Mês"] for r in records}), title="Mês"),
            y=alt.Y("Taxa (%):Q", title="Variação (%)"),
            color=alt.Color(
                "Grupo:N",
                legend=alt.Legend(orient="bottom", direction="vertical", columns=1, labelLimit=0),
            ),
            tooltip=["Grupo:N", "Mês:O", alt.Tooltip("Taxa (%):Q", format=".2f")],
        )
        .properties(height=360 + 22 * len({r["group_id"] for r in selected}))
    )


def comparison_chart_data(comparisons):
    records = [
        {
            "Grupo": GROUPS[code],
            "Período A (%)": float(c.a.compounded),
            "Período B (%)": float(c.b.compounded),
        }
        for code, c in comparisons.items()
    ]
    if any(
        not math.isfinite(row[key])
        for row in records
        for key in ("Período A (%)", "Período B (%)")
    ):
        return None
    return pd.DataFrame(records).set_index("Grupo")


def render_groups(rows, history):
    st.header("Inflação por grupos")
    st.caption("Brasil · IBGE/SIDRA 7060 · Nove grupos de despesas")
    if not rows:
        st.info("Não há dados dos grupos. Importe a amostra ou solicite a atualização.")
        return
    try:
        validate_group_rows(rows)
        available = sorted({row["period"] for row in rows})
        filter_group_rows(rows, list(GROUPS), available[0], available[-1])
    except RadarError as error:
        st.error(f"Dados dos grupos inválidos: {error}")
        st.info(
            "Preserve a base para conferência e reconfira a coleta antes de analisar os grupos."
        )
        return
    modes = {row["mode"] for row in rows}
    label = (
        "AMOSTRA INCLUÍDA"
        if modes == {"sample"}
        else "BASE CONSULTADA"
        if modes == {"live"}
        else "BASE MISTA"
    )
    st.info(f"{label} · Origem identificada por mês e grupo na tabela e no CSV.")
    st.caption(
        f"Cobertura dos grupos: {available[0]} a {available[-1]} · "
        f"{len(available)} meses · {len(rows)} registros."
    )
    codes = st.multiselect(
        "Grupos de despesas",
        list(GROUPS),
        default=["7170", "7445", "7625"],
        format_func=GROUPS.get,
        key="g_codes",
    )
    if not codes:
        st.info("Selecione pelo menos um grupo para consultar gráficos e comparações.")
        return
    left, right = st.columns(2)
    start = left.selectbox(
        "Mês inicial dos grupos", available, index=max(0, len(available) - 24), key="g_start"
    )
    end = right.selectbox("Mês final dos grupos", available, index=len(available) - 1, key="g_end")
    try:
        selected = filter_group_rows(rows, codes, start, end)
    except RadarError as error:
        st.error(str(error))
        return
    st.caption(f"Grupos aplicados: {start} a {end} · {len(codes)} grupos.")
    with st.expander("Como interpretar os grupos"):
        st.markdown(
            "As taxas mensais, no ano e em 12 meses são oficiais do IBGE. "
            "No ano começa em janeiro; 12 meses termina no mês da observação. "
            "Os filtros não redefinem essas janelas.\n\n"
            "O peso mensal representa a participação do grupo na composição do índice. "
            "O ranking ordena taxas de variação: maior taxa não implica maior contribuição "
            "ao IPCA. Pesos não são somados ao longo dos meses.\n\n"
            "A tabela 7060 não informa os acumulados em 12 meses de janeiro a novembro/2020. "
            "Esses campos aparecem como Não disponível e ficam vazios no CSV, sem virar zero.\n\n"
            "O acumulado do intervalo A/B é uma estimativa por composição das taxas mensais "
            "publicadas. Pode diferir do acumulado oficial por arredondamento. "
            "Diferenças são A − B em pontos percentuais, antes do arredondamento."
        )
        st.link_button("Consultar a tabela 7060", "https://sidra.ibge.gov.br/tabela/7060")
    labels = {
        "monthly": "Variação mensal",
        "year_to_date": "Acumulado no ano",
        "twelve_month": "Acumulado em 12 meses",
    }
    measure = st.selectbox(
        "Indicador do gráfico", list(labels), format_func=labels.get, key="g_measure"
    )
    st.subheader("Evolução dos grupos")
    if any(row[measure] is not None for row in selected):
        st.altair_chart(evolution_chart(selected, measure), width="stretch")
    else:
        st.info("Este indicador não está disponível para os meses selecionados.")
    st.subheader("Ranking mensal dos grupos selecionados")
    ranking_month = st.selectbox(
        "Mês do ranking",
        sorted({r["period"] for r in selected}),
        index=len({r["period"] for r in selected}) - 1,
        key="g_rank_month",
    )
    ranking = group_ranking(rows, codes, ranking_month)
    st.altair_chart(ranking_chart(ranking), width="stretch")
    st.caption(
        f"Ranking de {ranking_month} · ordem da maior para a menor taxa mensal. "
        "Taxas negativas indicam queda. Peso e taxa são medidas distintas."
    )
    st.dataframe(
        [
            {
                "Posição": index,
                "Grupo": GROUPS[row["group_id"]],
                "Mensal (%)": _rate(row["monthly"]),
                "No ano (%)": _rate(row["year_to_date"]),
                "12 meses (%)": _rate(row["twelve_month"]),
                "Peso no mês (%)": _rate(row["weight"]),
            }
            for index, row in enumerate(ranking, 1)
        ],
        hide_index=True,
        width="stretch",
        key="g_ranking",
    )

    st.subheader("Comparar períodos por grupo")
    modes = {
        "previous": "Período anterior de mesma duração",
        "year": "Mesmo período do ano anterior",
        "custom": "Escolher outro período",
    }
    mode = st.selectbox("Comparar grupos com", list(modes), format_func=modes.get, key="g_mode")
    if mode == "custom":
        bs, be = reference_period(start, end, "previous")
        if bs not in available or be not in available:
            bs, be = start, end
        left_b, right_b = st.columns(2)
        bs = left_b.selectbox(
            "Mês inicial B dos grupos", available, index=available.index(bs), key="g_bstart"
        )
        be = right_b.selectbox(
            "Mês final B dos grupos", available, index=available.index(be), key="g_bend"
        )
    else:
        bs, be = reference_period(start, end, mode)
    try:
        comparisons = group_comparisons(rows, codes, start, end, bs, be)
        comparison_csv = group_comparison_csv_bytes(comparisons)
    except RadarError as error:
        st.info(f"Comparação dos grupos indisponível: {error}")
    else:
        st.caption(f"Comparação dos grupos: A {start} a {end} · B {bs} a {be}.")
        first = next(iter(comparisons.values()))
        if not first.same_length:
            st.warning("Os períodos têm durações diferentes; os acumulados não foram anualizados.")
        if first.overlap:
            st.info("Os períodos se sobrepõem; meses comuns participam dos dois cálculos.")
        estimates = comparison_chart_data(comparisons)
        if estimates is None:
            st.info(
                "Gráfico comparativo indisponível: os acumulados excedem a capacidade numérica "
                "do gráfico. Os valores decimais continuam disponíveis na tabela e no CSV."
            )
        else:
            st.bar_chart(estimates, horizontal=True, stack=False, sort=False)
        st.caption("Acumulados estimados pela composição das taxas mensais publicadas.")
        st.dataframe(
            [
                {
                    "Grupo": GROUPS[code],
                    "Indicador": m.label,
                    "A (%)": _rate(m.a),
                    "B (%)": _rate(m.b),
                    "A − B (p.p.)": "Não disponível"
                    if m.difference is None
                    else format_points(m.difference),
                }
                for code, c in comparisons.items()
                for m in c.measures
            ],
            hide_index=True,
            width="stretch",
            key="g_comparison",
        )
        st.download_button(
            "Baixar CSV da comparação dos grupos",
            comparison_csv,
            file_name=f"grupos-comparacao-{start}-{end}-vs-{bs}-{be}.csv",
            mime="text/csv",
            key="g_comparison_csv",
            on_click="ignore",
        )
    try:
        period_csv = group_csv_bytes(selected)
        ranking_csv = group_csv_bytes(ranking)
    except RadarError as error:
        st.error(f"Exportação dos grupos indisponível: {error}")
    else:
        st.download_button(
            "Baixar CSV dos grupos",
            period_csv,
            file_name=f"grupos-{start}-a-{end}.csv",
            mime="text/csv",
            key="g_csv",
            on_click="ignore",
        )
        st.download_button(
            "Baixar CSV do ranking",
            ranking_csv,
            file_name=f"grupos-ranking-{ranking_month}.csv",
            mime="text/csv",
            key="g_ranking_csv",
            on_click="ignore",
        )
    st.caption(
        "Downloads usam os dados desta tela. Atualize a página para incorporar novas coletas."
    )
    with st.expander("Dados dos grupos e procedência"):
        st.dataframe(
            [
                {
                    "Mês": r["period"],
                    "Grupo": GROUPS[r["group_id"]],
                    "Mensal (%)": _rate(r["monthly"]),
                    "No ano (%)": _rate(r["year_to_date"]),
                    "12 meses (%)": _rate(r["twelve_month"]),
                    "Peso (%)": _rate(r["weight"]),
                    "Modo": r["mode"],
                    "Coletado em": r["retrieved_at"],
                    "SHA-256": r["raw_sha256"],
                    "Coleta ID": r["run_id"],
                }
                for r in selected
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("Histórico das coletas dos grupos"):
        st.dataframe(
            [
                dict(
                    zip(
                        (
                            "Coleta",
                            "Início UTC",
                            "Fim UTC",
                            "Modo",
                            "Situação",
                            "Novos",
                            "Corrigidos",
                            "Sem alteração",
                            "Detalhe",
                        ),
                        h,
                        strict=True,
                    )
                )
                for h in history
            ],
            hide_index=True,
            width="stretch",
        )
