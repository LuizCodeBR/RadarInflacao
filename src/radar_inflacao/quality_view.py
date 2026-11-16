"""Central responsiva; relatórios usam o mesmo snapshot que as tabelas."""

import math

import streamlit as st

from .audit import DATASETS, FIELDS, MAX_CHANGES
from .errors import RadarError
from .groups import GROUPS
from .quality import CHECKS, build_quality
from .quality_report import STAGES, changes_csv_bytes, quality_csv_bytes
from .report import _number
from .simulation import fingerprint, prepare_demo

LABELS = {
    "OK": "Verificações aprovadas",
    "ERROR": "Problema identificado",
    "WARNING": "Atenção",
    "UNKNOWN": "Não verificado",
    "EMPTY": "Sem dados",
    "INFO": "Informação",
}
RUN_LABELS = {"SUCCESS": "Concluída", "FAILED": "Falhou", "INTERRUPTED": "Interrompida"}
MODES = {"sample": "Amostra incluída", "live": "Consulta IBGE", "simulation": "Simulação offline"}


def _when(run, field):
    return "Não registrado" if run is None or run.get(field) is None else run[field]


def change_table(rows):
    return [
        {
            "Conjunto": DATASETS[r["dataset"]],
            "Mês": r["period"],
            "Grupo": GROUPS.get(r["group_id"], "Índice geral"),
            "Indicador": FIELDS[r["field"]],
            "Evento": "Inclusão" if r["kind"] == "ADDED" else "Alteração detectada",
            "Anterior (%)": "Não disponível" if r["old_value"] is None else _number(r["old_value"]),
            "Novo (%)": "Não disponível" if r["new_value"] is None else _number(r["new_value"]),
            "Detectado em": r["recorded_at"],
            "Modo": MODES[r["mode"]],
            "Coleta ID": r["run_id"],
            "SHA-256": r["raw_sha256"],
        }
        for r in rows
    ]


def render_quality(repository, root):
    st.header("Qualidade e atualização")
    st.caption("Situação da base local, verificações e mudanças detectadas entre coletas.")
    use_demo = st.toggle("Usar demonstração offline separada", key="quality_demo")
    if use_demo:
        st.warning(
            "SIMULAÇÃO OFFLINE · Valores alterados para demonstrar o histórico. "
            "Nenhum dado desta área foi consultado online agora. Sua base principal é preservada."
        )
        try:
            with st.spinner("Preparando exemplo local…"):
                repository = prepare_demo(root)
        except (RadarError, OSError, ValueError) as error:
            st.error(str(error))
            return
    key = fingerprint(repository.directory)
    st.subheader("Filtros do histórico")
    left, right = st.columns(2)
    dataset = left.selectbox(
        "Conjunto do histórico",
        ["all", *DATASETS],
        format_func=lambda x: DATASETS.get(x, "Todos"),
        key=f"q_dataset_{key}",
    )
    kind = right.selectbox(
        "Eventos do histórico",
        ["CHANGED", "ADDED", "all"],
        format_func={
            "CHANGED": "Alterações",
            "ADDED": "Inclusões",
            "all": "Inclusões e alterações",
        }.get,
        key=f"q_kind_{key}",
    )
    left, right = st.columns(2)
    start = (
        left.text_input(
            "Mês inicial do histórico (opcional)", placeholder="AAAA-MM", key=f"q_start_{key}"
        ).strip()
        or None
    )
    end = (
        right.text_input(
            "Mês final do histórico (opcional)", placeholder="AAAA-MM", key=f"q_end_{key}"
        ).strip()
        or None
    )
    group = None
    if dataset == "groups":
        group = st.selectbox(
            "Grupo do histórico",
            [None, *GROUPS],
            format_func=lambda x: GROUPS.get(x, "Todos os grupos"),
            key=f"q_group_{key}",
        )
    try:
        report = build_quality(
            repository.quality_snapshot(
                dataset=dataset, start=start, end=end, kind=kind, group_id=group
            )
        )
    except RadarError as error:
        st.error(str(error))
        return
    st.caption(f"Retrato consultado em {report['generated_at']} · horários com fuso UTC.")
    st.subheader("Situação das bases")
    for item in report["datasets"]:
        st.markdown(f"**{item['label']} · {LABELS[item['grade']]}**")
        a, b, c = st.columns(3)
        a.metric("Registros", item["count"])
        b.metric("Primeiro mês", item["start"] or "Sem dados")
        c.metric("Último mês", item["end"] or "Sem dados")
        attempt = item["latest_attempt"]
        st.write(
            "Origem: "
            + (", ".join(MODES.get(m, "Modo inválido") for m in item["modes"]) or "Sem registros")
        )
        attempt_label = (
            RUN_LABELS.get(attempt["status"], "Não registrada") if attempt else "Não registrada"
        )
        st.write(f"Última tentativa: {_when(attempt, 'started_at')} · {attempt_label}")
        st.write(f"Última publicação concluída: {_when(item['latest_success'], 'finished_at')}")
        if attempt and attempt["status"] != "SUCCESS":
            st.warning(
                f"Última tentativa: {RUN_LABELS.get(attempt['status'], attempt['status'])}. "
                f"Etapa: {STAGES.get(attempt['stage'], 'Anterior à central')}. "
                f"{attempt['error'] or 'Consulte o histórico.'}"
            )
        st.dataframe(
            [
                {
                    "Verificação": CHECKS[c["code"]],
                    "Resultado": LABELS[c["status"]],
                    "Detalhe": c["detail"],
                }
                for c in item["checks"]
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            f"Histórico detalhado iniciado em {item['baseline']['started_at']}. "
            f"{item['baseline']['existing_rows']} registros já existiam nessa data; "
            "mudanças anteriores não foram reconstruídas."
        )
    try:
        summary_csv = quality_csv_bytes(report)
    except RadarError as error:
        st.error(f"Relatório indisponível: {error}")
    else:
        st.download_button(
            "Baixar CSV da qualidade",
            summary_csv,
            "radar-qualidade.csv",
            mime="text/csv",
            key="quality_csv",
            on_click="ignore",
        )
    st.subheader("Mudanças detectadas")
    st.caption(
        "Filtros acima afetam somente o histórico; as verificações cobrem a base completa. "
        "Inclusões são registradas por indicador. Reconferências sem diferença não geram mudanças."
    )
    st.write(f"{report['total_changes']} eventos encontrados com estes filtros.")
    try:
        history_csv = changes_csv_bytes(report)
    except RadarError as error:
        st.info(str(error))
    else:
        if report["changes"]:
            pages = max(1, math.ceil(len(report["changes"]) / 50))
            page = st.number_input(
                "Página do histórico",
                min_value=1,
                max_value=pages,
                value=1,
                step=1,
                key=f"q_page_{key}_{dataset}_{kind}_{start}_{end}_{group}",
            )
            st.dataframe(
                change_table(report["changes"][(page - 1) * 50 : page * 50]),
                hide_index=True,
                width="stretch",
                key="quality_changes",
            )
            st.download_button(
                "Baixar CSV das mudanças filtradas",
                history_csv,
                "radar-mudancas.csv",
                mime="text/csv",
                key="changes_csv",
                on_click="ignore",
            )
        else:
            st.info("Nenhuma mudança encontrada. Use a demonstração offline para experimentar.")
    if report["truncated"]:
        st.warning(
            f"O filtro excede {MAX_CHANGES} eventos. Refine conjunto, mês ou grupo para exportar."
        )
    with st.expander("Tentativas recentes e limites"):
        st.dataframe(
            [
                {
                    "Conjunto": item["label"],
                    "Início": r["started_at"],
                    "Fim": r["finished_at"],
                    "Modo": MODES.get(r["mode"], "Não identificado"),
                    "Situação": RUN_LABELS.get(r["status"], r["status"]),
                    "Etapa": STAGES.get(r["stage"], "Anterior à central"),
                    "Novos": r["inserted"],
                    "Alterados": r["updated"],
                    "Sem alteração": r["unchanged"],
                    "Detalhe": r["error"],
                }
                for item in report["datasets"]
                for r in item["history"]
            ],
            hide_index=True,
            width="stretch",
        )
        st.write(
            "Verificações locais não consultam a internet. A disponibilidade refere-se à "
            "última leitura dos metadados, sem presumir novos dados a cada mudança de mês. "
            "Atualizar pelo IBGE continua sob demanda. Cada conjunto tem sua própria transação; "
            "uma atualização pode ter sucesso parcial. O histórico registra mudanças de valores, "
            "sem atribuir automaticamente uma revisão oficial ao IBGE."
        )
        st.write(
            "Os downloads correspondem a este retrato. Atualize a página para ver outra coleta. "
            "A primeira importação gera inclusões; bases existentes iniciam o histórico sem "
            "inventar mudanças anteriores. A conferência não é garantia contra adulteração "
            "do disco por quem tem acesso de escrita."
        )
