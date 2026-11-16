"""Comparação regional responsiva sobre um único retrato de dados."""

import altair as alt
import streamlit as st

from .analysis import format_points, format_rate, reference_period
from .area_report import area_comparison_csv_bytes, area_csv_bytes
from .areas import (
    AREAS,
    LOCATIONS,
    MEASURES,
    area_comparisons,
    area_ranking,
    filter_area_rows,
    validate_area_rows,
)
from .errors import RadarError


def _rate(value, points=False):
    return (
        "Não disponível"
        if value is None
        else (format_points(value) if points else format_rate(value))
    )


def evolution_chart(selected, measure):
    records = [
        {
            "Mês": r["period"],
            "Área": LOCATIONS[r["area_key"]],
            "Taxa (%)": None if r[measure] is None else float(r[measure]),
        }
        for r in selected
    ]
    return (
        alt.Chart(alt.Data(values=records))
        .mark_line()
        .encode(
            x=alt.X("Mês:O", sort=sorted({r["Mês"] for r in records})),
            y=alt.Y("Taxa (%):Q"),
            color=alt.Color(
                "Área:N",
                legend=alt.Legend(orient="bottom", direction="vertical", columns=1, labelLimit=0),
            ),
            tooltip=["Área:N", "Mês:O", alt.Tooltip("Taxa (%):Q", format=".2f")],
        )
        .properties(height=380 + 22 * len({r["area_key"] for r in selected}))
    )


def ranking_chart(ranking):
    records = [
        {
            "Área": AREAS[r["area_key"]],
            "Variação mensal (%)": float(r["monthly"]),
            "Diferença para o Brasil (p.p.)": float(r["differences"]["monthly"]),
        }
        for r in ranking
    ]
    return (
        alt.Chart(alt.Data(values=records))
        .mark_bar()
        .encode(
            y=alt.Y("Área:N", sort=[r["Área"] for r in records], axis=alt.Axis(labelLimit=260)),
            x=alt.X("Variação mensal (%):Q"),
            color=alt.condition(
                alt.datum["Variação mensal (%)"] < 0, alt.value("#ce653c"), alt.value("#087e8b")
            ),
            tooltip=[
                "Área:N",
                alt.Tooltip("Variação mensal (%):Q", format=".2f"),
                alt.Tooltip("Diferença para o Brasil (p.p.):Q", format=".2f"),
            ],
        )
        .properties(height=max(200, 32 * len(records)))
    )


def render_areas(rows, history):
    st.header("Comparar áreas do IPCA")
    st.caption("16 áreas pesquisadas e Brasil · Índice geral · IBGE / SIDRA 7060")
    if not rows:
        st.info("Importe a amostra regional ou solicite a atualização para consultar as áreas.")
        return
    try:
        validate_area_rows(rows)
        available = sorted({r["period"] for r in rows})
        filter_area_rows(rows, list(LOCATIONS), available[0], available[-1], brazil=True)
    except RadarError as error:
        st.error(f"Dados regionais inválidos: {error}")
        return
    modes = {r["mode"] for r in rows}
    label = (
        "AMOSTRA INCLUÍDA"
        if modes == {"sample"}
        else "BASE CONSULTADA"
        if modes == {"live"}
        else "BASE MISTA"
    )
    st.info(f"{label} · Origem de cada área e da referência do Brasil no CSV.")
    st.caption(f"Cobertura regional: {available[0]} a {available[-1]} · {len(rows)} registros.")
    with st.expander("Como interpretar áreas, diferenças e ranking"):
        st.write(
            "As dez regiões metropolitanas, cinco municípios e a área de Brasília são "
            "recortes específicos pesquisados pelo IBGE. O resultado de uma área não representa "
            "todo seu estado. O nível territorial e o código oficial acompanham o CSV. "
            "O ranking compara taxas de variação de um mesmo mês; não classifica custo de vida, "
            "preços absolutos ou contribuição para o IPCA."
        )
        st.write(
            "Diferença = taxa da área menos taxa do Brasil, em pontos percentuais. "
            "O Brasil é o resultado oficial da tabela 7060, não uma média simples das áreas. "
            "No ano e em 12 meses preservam suas janelas oficiais. Janeiro–novembro/2020 "
            "não têm acumulado de 12 meses nesta tabela: ausências ficam vazias, sem virar zero."
        )
        st.link_button("Consultar o IBGE / SIDRA 7060", "https://sidra.ibge.gov.br/tabela/7060")
    keys = st.multiselect(
        "Áreas pesquisadas",
        list(AREAS),
        default=["N7:3501", "N7:3301", "N6:5300108"],
        format_func=AREAS.get,
        key="a_keys",
    )
    if not keys:
        st.info("Selecione pelo menos uma área para consultar.")
        return
    left, right = st.columns(2)
    start = left.selectbox(
        "Mês inicial das áreas", available, index=max(0, len(available) - 24), key="a_start"
    )
    end = right.selectbox("Mês final das áreas", available, index=len(available) - 1, key="a_end")
    try:
        selected = filter_area_rows(rows, ["N1:1", *keys], start, end, brazil=True)
        period_csv = area_csv_bytes(rows, keys, start, end)
    except RadarError as error:
        st.error(f"Consulta regional indisponível: {error}")
        return
    st.caption(f"Áreas aplicadas: {start} a {end} · {len(keys)} áreas e referência Brasil.")
    measure = st.selectbox(
        "Indicador regional do gráfico", list(MEASURES), format_func=MEASURES.get, key="a_measure"
    )
    st.subheader("Evolução das áreas e do Brasil")
    if any(r[measure] is not None for r in selected):
        st.altair_chart(evolution_chart(selected, measure), width="stretch")
    else:
        st.info("Indicador indisponível para esses meses.")
    st.download_button(
        "Baixar CSV das áreas e diferenças",
        period_csv,
        file_name=f"areas-{start}-a-{end}.csv",
        mime="text/csv",
        key="a_csv",
        on_click="ignore",
    )
    st.subheader("Ranking mensal das áreas selecionadas")
    ranking_month = st.selectbox(
        "Mês do ranking regional",
        sorted({r["period"] for r in selected}),
        index=len({r["period"] for r in selected}) - 1,
        key="a_rank_month",
    )
    ranking = area_ranking(rows, keys, ranking_month)
    st.altair_chart(ranking_chart(ranking), width="stretch")
    st.caption(
        "Ordem da maior para a menor variação mensal; empates seguem a ordem fixa das áreas."
    )
    st.dataframe(
        [
            {
                "Posição": i,
                "Área": AREAS[r["area_key"]],
                **{MEASURES[f] + " (%)": _rate(r[f]) for f in MEASURES},
                **{
                    "Área − Brasil · " + MEASURES[f] + " (p.p.)": _rate(r["differences"][f], True)
                    for f in MEASURES
                },
            }
            for i, r in enumerate(ranking, 1)
        ],
        hide_index=True,
        width="stretch",
        key="a_ranking",
    )
    st.download_button(
        "Baixar CSV do ranking regional",
        area_csv_bytes(rows, keys, ranking_month, ranking_month, ranking=True),
        file_name=f"areas-ranking-{ranking_month}.csv",
        mime="text/csv",
        key="a_ranking_csv",
        on_click="ignore",
    )
    st.subheader("Comparar períodos por área")
    options = {
        "previous": "Período anterior de mesma duração",
        "year": "Mesmo período do ano anterior",
        "custom": "Escolher outro período",
    }
    mode = st.selectbox("Comparar áreas com", list(options), format_func=options.get, key="a_mode")
    if mode == "custom":
        left, right = st.columns(2)
        bs = left.selectbox(
            "Mês inicial B das áreas", available, index=available.index(start), key="a_bs"
        )
        be = right.selectbox(
            "Mês final B das áreas", available, index=available.index(end), key="a_be"
        )
    else:
        bs, be = reference_period(start, end, mode)
    try:
        comparisons = area_comparisons(rows, keys, start, end, bs, be)
        comparison_csv = area_comparison_csv_bytes(comparisons)
    except RadarError as error:
        st.info(f"Comparação regional indisponível: {error}")
    else:
        st.caption(f"Comparação regional: A {start} a {end} · B {bs} a {be}.")
        first = next(iter(comparisons.values()))
        if not first.same_length:
            st.warning("Os períodos têm durações diferentes; acumulados não foram anualizados.")
        if first.overlap:
            st.info("Os períodos se sobrepõem; meses comuns entram nos dois intervalos.")
        st.caption(
            "Acumulado do intervalo: estimativa por composição das taxas mensais publicadas."
        )
        st.dataframe(
            [
                {
                    "Área": LOCATIONS[key],
                    "Indicador": m.label,
                    "A (%)": _rate(m.a),
                    "B (%)": _rate(m.b),
                    "A − B (p.p.)": _rate(m.difference, True),
                }
                for key, c in comparisons.items()
                for m in c.measures
            ],
            hide_index=True,
            width="stretch",
            key="a_comparison",
        )
        st.download_button(
            "Baixar CSV da comparação regional",
            comparison_csv,
            file_name=f"areas-comparacao-{start}-{end}-vs-{bs}-{be}.csv",
            mime="text/csv",
            key="a_comparison_csv",
            on_click="ignore",
        )
    st.caption(
        "Downloads usam este retrato dos dados. Atualize a página para incorporar outra coleta."
    )
    with st.expander("Dados regionais e procedência"):
        st.dataframe(
            [
                {
                    "Mês": r["period"],
                    "Área": LOCATIONS[r["area_key"]],
                    "Área ID": r["area_key"],
                    **{MEASURES[f]: _rate(r[f]) for f in MEASURES},
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
    with st.expander("Tentativas regionais recentes"):
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
                            "Alterados",
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
