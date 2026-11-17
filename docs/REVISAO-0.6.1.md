# Revisão de segurança e concorrência — Radar da Inflação 0.6.1

16/11/2026. Revisão separada da implementação 0.6.0, por inspeção do código, reprodução dos defeitos e testes adversariais em bases isoladas. Não é auditoria externa nem certificação.

Projeto em D:/Projetos/RadarInflacao. Sem recurso pago, serviço novo, chave de API, agendamento, dependência nova ou extensão. Esquema 5 e amostras oficiais preservados. Não foi necessário atualizar os valores do IBGE.

## Achados reproduzidos e corrigidos

| Achado | Evidência anterior | Correção e alcance |
| --- | --- | --- |
| Procedência inválida aceita na escrita | Manifesto com URL de consulta divergente ou data fora do contrato era publicado como SUCCESS; o comparador recusava a base depois. Adaptador INPC com URL de outra tabela também podia publicar | Data e URL canônica verificadas antes do arquivo bruto/publicação. Tentativa FAILED preserva linhas, origem e mudanças anteriores. Fluxo compartilhado cobre os quatro conjuntos |
| Resposta lenta mantinha a operação ocupada | Fragmentos periódicos evitavam o timeout de inatividade; teste simulado completava 120 segundos sem recusa | Orçamento monotônico de 45 s por recurso, incluindo tentativas e esperas, conferido nas etapas de recebimento. Timeouts por operação continuam ativos |
| Associação de medidas dependente de ordem | Inverter a ordem do mapa ID→campo trocava mensal e 12 meses, mesmo com IDs válidos | Construção por nome de campo; inversão do mapa e da resposta preserva os valores em IPCA e INPC |
| Gráfico sem marca em um único mês | Duas séries com um ponto cada não formavam linhas visíveis | Marcadores explícitos sobre a evolução, nas três medidas; diferença mantém barras e sinal |
| Indicador visual divergente após intervalo inválido | A validação removia o seletor da tela. Ao recuperar o período, o navegador podia mostrar Mensal enquanto o cálculo permanecia em 12 meses | Seletor permanece montado antes da validação do período; escolha preservada, rótulo, valores e gráficos coerentes |


Os testes de procedência usam cópias locais modificadas/adaptadores controlados. Não representam exploração remota nem demonstram modificação dos dados oficiais. A dependência da ordem era um defeito latente de manutenção: os mapas originais já estavam na ordem correta; as amostras não continham taxas trocadas. O timeout anterior já limitava inatividade; faltava limitar o tempo observado de recebimento contínuo.

## Testes adicionados

46 casos em tests/test_index_review.py, sem remover os 490 anteriores:

- Sete casos de procedência inválida em importação/atualização, verificando recusa antes de publicar e preservação dos valores/histórico.
- Dois casos de associação por ID/nome, independentes de ordem da resposta e do dicionário.
- Três medidas em gráfico com um mês e dois pontos; dois cenários de seleção preservada depois de um intervalo inválido.
- Três fontes com resposta lenta, seis cenários de retentativas sem reiniciar o orçamento, cliente padrão sem injeção e falha INPC liberando o banco com etapa DOWNLOAD/FAILED.
- Doze combinações de fórmula/controle/procedência em IPCA ou INPC: recusa de CSV de período e de comparação, inclusive adulteração fora de A.
- Cinco taxas sintéticas extremas, de -100% a 999999,999999%, verificadas contra aritmética racional independente (Fraction) durante 24 meses. Decimal global com precisão/traps restritivos não altera cálculos/CSV. Esses valores não entram no banco principal.
- Dois processos reais de escrita IPCA, com commit e encerramento abrupto. Leitura nova e escrita INPC recebem BusyError; CSVs preparados permanecem idênticos. Commit publica uma alteração e seu evento; interrupção desfaz e registra INTERRUPTED na próxima abertura.
- Dois tipos de CSV em corrida entre processos. Exatamente um publica, outro recebe arquivo existente; resultado é um dos arquivos completos, sem mistura/sobrescrita/temporário residual.

Treze casos iniciais falharam na versão 0.6.0 e passaram após a correção. A inspeção visual revelou a divergência do seletor; dois testes adicionais reproduziram sua desmontagem em intervalo inválido e passaram após a correção. As reproduções usam relógio simulado; não esperam minutos nem acessam a rede. Os primeiros 44 casos passaram em 6,87 s na execução direcionada. Uma execução intermediária com comparador/coleta/pipeline terminou com 136 aprovados; a integração regional detectada durante o ajuste foi corrigida adicionando seu construtor de URL, sem enfraquecer testes.

A verificação final direcionada de revisão, comparador e aplicação terminou com 114 aprovados em 79,58 s. O ensaio do navegador confirmou a seleção preservada ao recuperar o intervalo, a troca explícita para Mensal e os valores 0,14% / 0,22% do mês único. As capturas finais foram inspecionadas.

## Resultados da entrega

- Windows / Python 3.13.14, testar.cmd: **536 aprovados**, 373,68 s; Ruff aprovado.
- Windows / Python 3.12.13: **536 aprovados**, 373,52 s.

São 490 testes anteriores + 46 novos. As suítes finais foram executadas depois da correção do seletor, em diretórios separados, simultaneamente; os tempos não são comparação de desempenho entre versões. CI Windows/Linux continua configurada, mas não foi executada remotamente.

- Chromium: desktop 1440 pixels e mobile emulado 412 pixels; evolução, barras positivas/negativas, filtros, três medidas, comparação com ano anterior e recusa de intervalo invertido. CSV de período com 24 meses, recorte com três meses, mês único e A/B com quatro linhas. Seletor e valores conferidos após recuperar intervalo inválido; dois pontos visíveis no mês único. Quatro capturas atualizadas e inspecionadas; sem transbordamento da página.
- Instalação limpa com preparar.cmd no D:, Python 3.13, sem nova dependência. Importação/reimportação de 82 IPCA + 738 grupos + 1394 áreas + 82 INPC; 7626 inclusões históricas sem duplicação. Qualidade com 16 verificações e histórico INPC com 246 inclusões. Painel final abriu sem exceções e preservou o indicador ao corrigir o intervalo.
- Os oito arquivos da base principal, exceto radar.lock, permaneceram byte a byte idênticos por SHA-256. Amostras e dependências permanecem iguais ao conteúdo versionado da 0.6.0; manifestos respeitam a conversão de quebras de linha do Git no Windows. Conferidos 21 documentos e 95 links locais.
- O servidor de revisão usou somente uma cópia da base e foi encerrado após a verificação visual. Porta 8508 sem servidor ao concluir essa etapa.

Evidências locais: .cache/revisao061-antes.log, revisao061-ui-antes.log, revisao061-tests.log, revisao061-ui-final.log, testes061-final313.log, testes061-final312.log, navegador061-final.log, instalacao061.log, instalacao061-final.log, verificacao061.log e pacote061.log (verificação do ZIP extraído). Avisos de ScriptRunContext vêm da execução programática do AppTest; as asserções de interface passaram.

Entrega fonte preparada em D:/Projetos/Entregas/RadarInflacao-0.6.1, com ZIP, cópia extraída, SHA-256 e identificação do commit/tag local. O pacote exclui banco pessoal, ambientes, caches, exportações e Git. Não há remoto configurado nem publicação no GitHub.

## Preservação e limites

Cópia da base feita sob FileLock em .cache/revisao061-base; hashes iniciais em .cache/principal061-hashes.json. Todas as execuções usam bases isoladas. Esquema 5, formatos de CSV, quatro conjuntos, amostras e dependências permanecem.

O orçamento HTTP é cooperativo: é verificado antes da tentativa, após cabeçalhos, entre blocos decodificados e ao concluir. Uma chamada bloqueada/decodificação não é interrompida por um temporizador externo; o limiar pode ser ultrapassado até a próxima verificação, e os timeouts HTTP continuam relevantes. Não é limite rígido de toda atualização, que consulta vários recursos. Não é proteção absoluta contra qualquer padrão de transporte/compressão.

A concorrência continua sendo para processos da aplicação que respeitam o bloqueio, em disco local. Não há garantia para pasta de rede/sincronizada, processos externos que ignorem o lock, múltiplos servidores ou qualquer falha física. Os quatro conjuntos têm publicações separadas; atualização parcial é informada. Hashes identificam a resposta, não assinam criptograficamente todo o banco contra quem pode editar o disco.

Downloads usam bytes preparados e on_click=ignore. O arquivo CLI requer suporte a hard links locais. Não houve execução em Excel/LibreOffice, celular físico, Linux/macOS nativo ou CI remota nesta revisão.

Referências primárias: [HTTPX — timeouts por operação](https://www.python-httpx.org/advanced/timeouts/), [DuckDB — concorrência](https://www.duckdb.org/docs/current/connect/concurrency), [Streamlit — ciclo de vida dos seletores](https://docs.streamlit.io/develop/concepts/architecture/widget-behavior), [Vega-Lite — linhas e marcadores](https://vega.github.io/vega-lite/docs/line.html), [OWASP — CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection).

[Guia do comparador](INDICES.md) · [Arquitetura](ARQUITETURA.md) · [Validação da implementação 0.6.0](VALIDACAO-0.6.0.md).
