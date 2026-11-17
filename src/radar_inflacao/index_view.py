"""Painel nacional responsivo: evolução, diferenças e comparação de períodos."""

import altair as alt
import streamlit as st

from .analysis import format_points, format_rate, reference_period
from .errors import RadarError
from .index_report import comparison_records, index_comparison_csv_bytes, index_csv_bytes
from .indices import INDICES, MEASURES, index_comparisons, index_pairs, validate_indices


def evolution_chart(pairs, measure):
    records = [
        {"Mês": p["period"], "Índice": label, "Taxa (%)": float(p[key][measure])}
        for p in pairs
        for key, label in INDICES.items()
    ]
    return (
        alt.Chart(alt.Data(values=records))
        .mark_line(point=True)
        .encode(
            x=alt.X("Mês:O", sort=[p["period"] for p in pairs]),
            y=alt.Y("Taxa (%):Q"),
            color=alt.Color(
                "Índice:N",
                scale=alt.Scale(domain=["IPCA", "INPC"], range=["#087e8b", "#ce653c"]),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["Mês:O", "Índice:N", alt.Tooltip("Taxa (%):Q", format=".2f")],
        )
        .properties(height=350)
    )


def difference_chart(pairs, measure):
    records = [
        {"Mês": p["period"], "INPC − IPCA (p.p.)": float(p["differences"][measure])} for p in pairs
    ]
    return (
        alt.Chart(alt.Data(values=records))
        .mark_bar()
        .encode(
            x=alt.X("Mês:O", sort=[p["period"] for p in pairs]),
            y=alt.Y(field=r"INPC − IPCA (p\.p\.)", type="quantitative", title="INPC − IPCA (p.p.)"),
            color=alt.condition(
                alt.datum["INPC − IPCA (p.p.)"] >= 0, alt.value("#ce653c"), alt.value("#087e8b")
            ),
            tooltip=[
                "Mês:O",
                alt.Tooltip(
                    field=r"INPC − IPCA (p\.p\.)",
                    type="quantitative",
                    title="INPC − IPCA (p.p.)",
                    format="+.2f",
                ),
            ],
        )
        .properties(height=250)
    )


def render_indices(indices):
    st.header("IPCA × INPC nacional")
    st.caption("Duas perspectivas da inflação · Brasil · IBGE / SIDRA 1737 e 1736")
    try:
        validate_indices(indices)
    except RadarError as error:
        st.error(f"Dados dos índices inválidos: {error}")
        return
    if any(not rows for rows in indices.values()):
        st.info("Importe as amostras dos dois índices ou solicite uma atualização.")
        return
    starts, ends = {}, {}
    for key, label in INDICES.items():
        months = sorted(r["period"] for r in indices[key])
        starts[key], ends[key] = months[0], months[-1]
        st.caption(f"{label}: {months[0]} a {months[-1]} · {len(months)} registros.")
    if len(set(starts.values())) != 1 or len(set(ends.values())) != 1:
        st.warning(
            "Os índices têm coberturas diferentes. Os filtros mostram a união dos meses; "
            "a consulta só é gerada quando os dois cobrem todo o intervalo escolhido."
        )
    modes = {r["mode"] for rows in indices.values() for r in rows}
    label = (
        "AMOSTRAS INCLUÍDAS"
        if modes == {"sample"}
        else "BASES CONSULTADAS"
        if modes == {"live"}
        else "BASES MISTAS"
    )
    st.info(f"{label} · Procedência separada de IPCA e INPC no CSV do período.")
    with st.expander("Entenda os índices e as diferenças"):
        st.write(
            "O IPCA considera famílias com renda de 1 a 40 salários mínimos, qualquer que "
            "seja a fonte. O INPC considera famílias com renda de 1 a 5 salários mínimos, "
            "cuja pessoa de referência é assalariada. Os recortes e pesos diferem: os índices "
            "representam populações pesquisadas, não a inflação individual de cada pessoa."
        )
        st.write(
            "Diferença = INPC menos IPCA, em pontos percentuais. Positiva indica INPC maior; "
            "negativa indica IPCA maior. Exemplo fictício: 0,60% − 0,40% = +0,20 p.p. "
            "No ano e em 12 meses mantêm as janelas oficiais encerradas em cada mês; "
            "mudar o início do filtro não redefine esses acumulados."
        )
        st.link_button(
            "Definições dos índices — IBGE", "https://www.ibge.gov.br/explica/inflacao.php"
        )
        st.link_button("Fonte do IPCA — tabela 1737", "https://sidra.ibge.gov.br/tabela/1737")
        st.link_button("Fonte do INPC — tabela 1736", "https://sidra.ibge.gov.br/tabela/1736")
    available = sorted({r["period"] for rows in indices.values() for r in rows})
    left, right = st.columns(2)
    start = left.selectbox(
        "Mês inicial dos índices", available, index=max(0, len(available) - 24), key="i_start"
    )
    end = right.selectbox("Mês final dos índices", available, index=len(available) - 1, key="i_end")
    # Mantém o widget montado durante um intervalo inválido, sem perder a escolha.
    measure = st.selectbox(
        "Indicador dos índices", list(MEASURES), format_func=MEASURES.get, key="i_measure"
    )
    try:
        pairs = index_pairs(indices, start, end)
        period_csv = index_csv_bytes(indices, start, end)
    except RadarError as error:
        st.error(f"Consulta dos índices indisponível: {error}")
        return
    duration = "1 mês" if len(pairs) == 1 else f"{len(pairs)} meses"
    st.caption(f"Período aplicado aos índices: {start} a {end} · {duration} em ambos.")
    last = pairs[-1]
    st.subheader(f"{MEASURES[measure]} · {end}")
    a, b, c = st.columns(3)
    a.metric("IPCA", format_rate(last["ipca"][measure]))
    b.metric("INPC", format_rate(last["inpc"][measure]))
    c.metric("INPC − IPCA", format_points(last["differences"][measure]))
    st.subheader("Evolução do IPCA e do INPC")
    st.altair_chart(evolution_chart(pairs, measure), width="stretch")
    st.subheader("Diferença INPC − IPCA")
    st.altair_chart(difference_chart(pairs, measure), width="stretch")
    st.caption("Barras acima de zero: INPC maior. Abaixo de zero: IPCA maior.")
    st.dataframe(
        [
            {
                "Mês": p["period"],
                **{
                    f"{label} · {MEASURES[f]} (%)": format_rate(p[key][f])
                    for key, label in INDICES.items()
                    for f in MEASURES
                },
                **{
                    f"INPC − IPCA · {MEASURES[f]} (p.p.)": format_points(p["differences"][f])
                    for f in MEASURES
                },
            }
            for p in pairs
        ],
        hide_index=True,
        width="stretch",
        key="i_values",
    )
    st.download_button(
        "Baixar CSV IPCA × INPC",
        period_csv,
        f"ipca-inpc-{start}-a-{end}.csv",
        mime="text/csv",
        key="i_csv",
        on_click="ignore",
    )
    st.subheader("Comparar períodos dos índices")
    options = {
        "previous": "Período anterior de mesma duração",
        "year": "Mesmo período do ano anterior",
        "custom": "Escolher outro período",
    }
    mode = st.selectbox(
        "Comparar índices com", list(options), format_func=options.get, key="i_mode"
    )
    if mode == "custom":
        left, right = st.columns(2)
        bs = left.selectbox(
            "Mês inicial B dos índices", available, index=available.index(start), key="i_bs"
        )
        be = right.selectbox(
            "Mês final B dos índices", available, index=available.index(end), key="i_be"
        )
    else:
        bs, be = reference_period(start, end, mode)
    try:
        comparisons = index_comparisons(indices, start, end, bs, be)
        comparison_csv = index_comparison_csv_bytes(comparisons)
    except RadarError as error:
        st.info(f"Comparação dos índices indisponível: {error}")
    else:
        st.caption(f"Índices comparados: A {start} a {end} · B {bs} a {be}.")
        first = comparisons["ipca"]
        if not first.same_length:
            st.warning("Os períodos têm durações diferentes; acumulados não foram anualizados.")
        if first.overlap:
            st.info("Os períodos se sobrepõem; meses comuns entram nos dois intervalos.")
        st.caption(
            "Acumulado do intervalo: estimativa por composição das taxas mensais publicadas. "
            "Pode diferir do acumulado oficial calculado com números-índice. "
            "As medidas oficiais usam o último mês de cada período."
        )
        st.dataframe(
            comparison_records(comparisons, display=True),
            hide_index=True,
            width="stretch",
            key="i_comparison",
        )
        st.download_button(
            "Baixar CSV da comparação IPCA × INPC",
            comparison_csv,
            f"ipca-inpc-comparacao-{start}-{end}-vs-{bs}-{be}.csv",
            mime="text/csv",
            key="i_comparison_csv",
            on_click="ignore",
        )
    st.caption(
        "Downloads usam este retrato dos dados; atualize a página para incorporar outra coleta."
    )
    with st.expander("Procedência dos índices no período"):
        st.dataframe(
            [
                {
                    "Mês": p["period"],
                    "Índice": label,
                    "Modo": p[key]["mode"],
                    "Coletado em": p[key]["retrieved_at"],
                    "Coleta ID": p[key]["run_id"],
                    "SHA-256": p[key]["raw_sha256"],
                }
                for p in pairs
                for key, label in INDICES.items()
            ],
            hide_index=True,
            width="stretch",
        )
