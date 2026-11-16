# Revisão de segurança e concorrência — Radar da Inflação 0.4.1

16/11/2026. Revisão separada da implementação 0.4.0, mediante leitura do código, reprodução de falhas em bases isoladas e testes adversos. Não é auditoria externa, certificação ou garantia de ausência de vulnerabilidades.

Trabalho em D:/Projetos/RadarInflacao. Sem conta, serviço pago, atualização online do IBGE, agendamento ou dependência nova. Esquema 3 preservado, sem nova migração.

## Achados corrigidos

| Achado | Antes | Correção |
| --- | --- | --- |
| Histórico incompleto por vínculo ausente | INNER JOIN podia ocultar eventos embora a contagem os incluísse; CSV parecia completo | LEFT JOIN mantém o evento detectável; leitura sinaliza vínculo inválido e exportador recusa arquivo inconsistente |
| Qualidade aprovada com procedência inconsistente | Observações ligadas a coleta sem sucesso e metadados com modo/data/hash inválidos podiam não receber erro | Validação de status, identificação, datas, etapa e referência; procedência inclui vínculos de publicações/histórico |
| Contrato incompleto do CSV | Total, duplicação e correspondência aos filtros não eram verificados; última publicação era conferida só pela data | Recusa de total divergente, duplicação, filtro divergente, coleta anterior ausente/malsucedida/igual à atual e publicação não concluída |
| Robustez diante de valores inválidos | Comparação de NaN em alteração ou ordenação de modos mistos inválidos podia interromper a central | Validação numérica antes da comparação; diagnóstico controlado de procedência |
| Demonstração aceita sem banco e podia virar base principal | Marcador completo bastava; RADAR_DATA_DIR podia apontar o painel/atualização para o cenário | Banco e execuções simuladas obrigatórios; marcador estrito e limitado; bloqueio de mutações na pasta reservada |
| Inconsistência estrutural sem explicação | Ausência do início do histórico provocava erro de índice | Erro de domínio explicado, sem apagar nem reconstruir dados |

São problemas de integridade e isolamento no aplicativo local. Os ensaios de banco corrompido usam escrita direta nas bases temporárias; isso não demonstra acesso remoto ao banco. A aplicação permanece vinculada a 127.0.0.1 por padrão.

## Método e regressões

17 casos iniciais foram executados contra a versão anterior e reproduziram as lacunas (log revisao041-antes.log). Após as correções, o arquivo tests/test_quality_review.py reúne 48 casos novos, somados aos 268 anteriores.

Cenários novos incluem eventos órfãos, coletas malsucedidas, vínculo anterior ausente/igual/invalidado, dia do mês oculto por formatação, metadados inválidos, contagens incoerentes, duplicações, filtros divergentes, valores NaN/sNaN/Infinity, fórmulas em texto, aspas/delimitadores, marcador malformado ou excessivo, arquivos em hard link, pasta de demonstração reservada e mensagens da interface.

Consulta e exportação explícitas da demonstração continuam funcionando. Última publicação e referência são preservadas mesmo após 21 falhas posteriores. A referência de disponibilidade continua significando a última consulta conhecida, não confirmação em tempo real.

## Concorrência

- Pipeline nacional real em outro processo, pausado depois da escrita e antes do commit. Leituras novas recebem BusyError; os dois CSVs já preparados mantêm exatamente seus bytes.
- Ao concluir, valores e evento aparecem juntos. Ao encerrar o processo, ambos são desfeitos e a tentativa vira INTERRUPTED na reabertura.
- Os cenários anteriores equivalentes para os nove grupos continuam na suíte.
- Dois processos disputam o mesmo destino com relatórios diferentes: exatamente um publica, o outro encontra arquivo existente; nunca se misturam bytes nem se substitui o vencedor.
- Duas preparações da demonstração: a segunda recebe BusyError. Se a primeira for encerrada, marcador incompleto e banco são preservados; não há reinício destrutivo automático.

Os downloads continuam usando bytes preparados e on_click="ignore". A legenda Histórico aplicado explicita o recorte; é necessário aplicar a edição do mês e aguardar antes de baixar.

## Resultados

- Windows / Python 3.13.14, testar.cmd: **316 aprovados**, 232,78 s; Ruff aprovado.
- Windows / Python 3.12.13: **316 aprovados**, 231,86 s.
- Revisão direcionada: 48 aprovados em 21,60 s. 17 casos de reprodução iniciais falhavam na versão anterior.
- Após o ajuste final exclusivamente textual da legenda dos filtros, os dois fluxos afetados da interface passaram novamente (20,53 s); Ruff permaneceu aprovado.
- Chromium: desktop de 1440 pixels e celular emulado de 412 pixels, sem transbordamento da página. Downloads, origem simulada, atualização desabilitada, filtros e recusa de mês inválido conferidos. Capturas atualizadas e inspecionadas.
- Preparação limpa com preparar.cmd e Python 3.13 no D: aprovada. Importação/reimportação: 82+738 registros, 3198 inclusões sem duplicação; CSVs, cenário separado e painel passaram. Atualização indevida da demonstração foi recusada.
- As suítes completas usaram pastas temporárias separadas e rodaram simultaneamente. Tempos não são comparação de desempenho entre versões.

O primeiro acionamento do navegador ocorreu antes de o servidor estar pronto; o roteiro foi executado após o health check responder. Uma execução intermediária registrou WinError 10054 no fechamento de conexão; a execução final do navegador passou, com health check 200 e sem esse aviso no log final. Não foi necessário alterar dependências.

Logs locais: .cache/revisao041-antes.log, revisao041-tests.log, testes041-313.log, testes041-312.log, testes041-ui-final.log, navegador041-final.log, instalacao041.log e instalacao041-smoke.log.

## Preservação e distribuição

A base principal foi copiada sob o bloqueio e validada em .cache/revisao041-base. Seus arquivos originais mantiveram os mesmos SHA-256: 82 observações nacionais, 738 dos grupos e esquema 3, sem modificação nem nova migração. A verificação de procedência não encontrou vínculos inválidos nessa cópia.

A disponibilidade da instalação principal continua Não verificado porque suas consultas são anteriores ao registro introduzido na central. Não houve consulta online ao IBGE para alterar esse estado. Nenhuma mudança retroativa foi inventada. Evidências: .cache/preservacao041.log e principal041-hashes.json.

Pacote fonte da entrega: D:/Projetos/Entregas/RadarInflacao-0.4.1/RadarInflacao-0.4.1-fonte.zip. Inclui código, testes, amostras, instruções e capturas; exclui ambientes, caches, banco e exportações pessoais. O pacote extraído é verificado com importação, CSVs e demonstração. Git/tag permanecem locais; não há remoto configurado ou publicação online.

## Limites e referências

- Testes de concorrência com disco local Windows/NTFS. Pastas de rede/sincronizadas e programas externos que ignorem o bloqueio estão fora da garantia.
- Não houve execução nativa Linux/macOS, celular físico, execução remota da CI ou teste de abertura de fórmulas em Excel/LibreOffice.
- A validação dos caminhos da demonstração não impede um adversário com escrita no disco de trocar caminhos durante a operação. Não é isolamento do sistema operacional.
- O histórico não é assinado nem inviolável. Hash com formato válido não autentica sozinho o conteúdo. A central não reconstrói toda a história a partir dos brutos e não recupera alterações anteriores à versão 0.4.0.
- O índice geral e os grupos mantêm transações separadas. Uma atualização conjunta pode ter sucesso parcial, informado pela aplicação.
- A exportação exige até 10000 eventos por recorte e publicação local por hard link; não se afirma durabilidade contra qualquer queda de energia.

Regras de texto/formato foram confrontadas com a [orientação da OWASP sobre CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection). O uso de bytes preparados e a necessidade de aplicar campos pendentes correspondem ao comportamento documentado de [st.download_button](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button). Os testes verificam a serialização; transformações posteriores de outro programa podem alterar o arquivo.

[Guia de uso](QUALIDADE.md) · [Arquitetura](ARQUITETURA.md) · [Validação anterior](VALIDACAO-0.4.0.md).
