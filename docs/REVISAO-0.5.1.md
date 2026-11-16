# Revisão de segurança e concorrência — Radar da Inflação 0.5.1

16/11/2026. Revisão separada da implementação 0.5.0, com leitura do código, reprodução de falhas e ensaios em bases isoladas. Não é auditoria de terceiro, certificação ou garantia de ausência de vulnerabilidades.

Projeto em D:/Projetos/RadarInflacao. Sem recurso pago, conta adicional, serviço externo novo, agendamento ou dependência nova. Esquema 4 preservado. As amostras oficiais incluídas não foram modificadas; não foi necessário consultar novos valores do IBGE.

## Achados e correções

| Achado | Comportamento anterior | Correção |
| --- | --- | --- |
| Procedência não validada em B | Comparações aceitavam registros de B com hash, UUID, modo ou data inválidos, embora o CSV de A validasse sua origem | Todo o retrato regional passa pelo mesmo contrato antes de comparação, ranking, filtro e exportação |
| Área e Brasil de coletas incompatíveis | Alteração local podia relacionar uma área a uma coleta e o Brasil a outra no mesmo mês | Exige identidade comum de coleta por mês: ID, modo, data, hash, janela e finalização; meses distintos continuam podendo ter coletas distintas |
| Publicação local inconsistente | Status sem sucesso, finalização ausente, data fora da coleta e dia incorreto ocultado pela formatação podiam chegar ao relatório | Leitura conserva esses atributos e valida dia, conclusão, janela e URL canônica; junções preservam registros inválidos para diagnóstico |
| Política HTTP dependia do cliente recebido | Um cliente externo com redirecionamentos habilitados ou timeout desativado enfraquecia o coletor | Cada requisição força redirecionamentos desabilitados e limites de conexão/leitura, inclusive com cliente injetado |
| Metadados regionais acoplados aos grupos | Mudança em categorias/peso não utilizados ou ordem de classificações podia bloquear uma consulta regional válida | Contrato regional próprio para tabela, frequência, três medidas, níveis e categoria Índice geral, encontrada por ID |

Os três primeiros itens são falhas de integridade diante de dados locais inconsistentes. As reproduções alteram cópias temporárias diretamente; não demonstram invasão remota. O cliente HTTP padrão já recusava redirecionamentos; o teste novo cobre a configuração alternativa. A aplicação mantém 127.0.0.1 como endereço padrão.

A validação não altera taxas nem inventa valores ausentes. Janeiro–novembro/2020 continuam sem acumulado de 12 meses. Brasil continua sendo a referência oficial da tabela 7060. Ranking continua sendo de variação mensal, não de preços absolutos ou custo de vida.

## Regressões e concorrência

23 casos executados antes da correção reproduziram as lacunas. O arquivo tests/test_area_review.py passa a reunir 49 casos adicionais aos 371 existentes. Nenhum teste anterior foi removido.

- Procedência malformada em B, identidades divergentes entre área/Brasil, dados associados a publicação malsucedida ou sem finalização e dia oculto pela formatação.
- Decimais não finitos, ausências indevidas, identificadores e datas inválidos, com contexto decimal restritivo sem efeitos colaterais.
- Resposta HTTP de redirecionamento com cliente permissivo: uma única requisição e recusa, sem alcançar o destino alternativo. Timeout conferido no próprio pedido simulado.
- Metadados estritos e independentes dos grupos; atualização incremental legítima mantém amostra/live em meses diferentes.
- Gráfico sintético de 20400 pontos (1200 meses × 17 localidades) sem alterar a configuração global do Altair; valores negativos, diferenças e ausência histórica preservados.
- Interface e CLI recusam dados inválidos antes de criar CSV ou gráficos, com mensagem controlada.
- Pipeline real em outro processo altera São Paulo e Brasil, pausa depois das escritas e antes do commit. Outro leitor/escritor recebe BusyError. Os três CSVs regionais e o histórico já preparados permanecem idênticos.
- Commit confirma as duas alterações juntas; encerramento do processo desfaz ambas e a tentativa passa a INTERRUPTED. Esses números são sintéticos e limitados ao teste.
- Dois processos disputam um CSV regional com conteúdos diferentes: exatamente um publica; o outro recebe arquivo existente. Sem substituição, mistura de bytes ou temporários abandonados.

A região, o Brasil e seus eventos usam a mesma transação regional. Nacional, grupos e áreas continuam sendo três publicações independentes, com possibilidade de resultado parcial informado.

## Resultados

- Windows / Python 3.13.14, testar.cmd: **420 aprovados**, 413,26 s; Ruff aprovado.
- Windows / Python 3.12.13: **420 aprovados**, 414,51 s.
- Revisão direcionada: **49 aprovados**, 43,92 s. Os 23 casos de reprodução inicial falhavam na 0.5.0; todos passaram depois das correções.
- Compatibilidade direcionada: 94 aprovados (primeiros 23 da revisão, 55 das áreas e 16 do coletor HTTP).
- Chromium: desktop 1440 pixels e celular emulado 412 pixels; três downloads com BOM e quantidades esperadas, filtros aplicados e recusa de intervalo invertido. Capturas atualizadas e inspecionadas; sem transbordamento da página.
- Preparação limpa por preparar.cmd no D:, Python 3.13: passou. Importação/reimportação de 82+738+1394 registros e 7380 inclusões históricas sem duplicação. CSV de período com 48 linhas, ranking com 16, A/B com 64; qualidade com 12 verificações e histórico de São Paulo com 246 inclusões.
- Painel da instalação limpa abriu sem exceções com os três downloads regionais. A CLI recusou sobrescrever o arquivo já exportado.

As suítes completas usaram diretórios de teste independentes e foram executadas simultaneamente; os tempos não são um comparativo de desempenho entre Python 3.12 e 3.13. A CI permanece configurada para Windows/Linux, mas não foi executada remotamente.

Evidências locais em .cache: revisao051-antes.log, revisao051-target1.log, revisao051-tests.log, testes051-313.log, testes051-312.log, navegador051-final.log, instalacao051.log e instalacao051-smoke.log. O aviso de ScriptRunContext no ensaio de instalação vem do uso programático do AppTest; as asserções de interface passaram.

## Preservação e distribuição

Cópia da base principal preparada sob bloqueio em .cache/revisao051-base. A cópia contém 82 observações nacionais, 738 dos grupos e 1394 regionais, esquema 4. A análise regional e sua procedência passaram; os avisos anteriores de disponibilidade nacional/grupos permanecem, pois não houve coleta para atualizá-los.

Os hashes de todos os arquivos originais de data, exceto radar.lock, permaneceram idênticos na conferência final (.cache/principal051-hashes.json e verificacao051.log). Não foi realizada migração nem reimportação na base principal. Os formatos dos três CSVs regionais permanecem. Os campos adicionais da leitura servem à validação interna.

Pacote fonte: D:/Projetos/Entregas/RadarInflacao-0.5.1/RadarInflacao-0.5.1-fonte.zip. Inclui código, testes, documentação, capturas e amostras. Exclui banco pessoal, ambientes, caches, exportações e pasta Git. A entrega acompanha SHA-256 e identificação do commit/tag local. A verificação do ZIP extraído fica em .cache/pacote051.log.

O servidor de navegador temporário usou uma base separada e foi encerrado após os testes. Nenhum recurso de hospedagem foi criado. O repositório continua sem remoto configurado; não houve publicação no GitHub.

## Limites e referências

- Revisão e concorrência em Windows/disco local. Não houve teste nativo Linux/macOS, celular físico, CI remota ou execução de arquivos no Excel/LibreOffice.
- A validação de identidade não autentica criptograficamente todo o banco contra um adversário que pode editar seus arquivos. Não há assinatura dos dados nem reconstrução completa de taxas a partir dos brutos em toda leitura.
- Processos externos que ignorem o bloqueio e pastas de rede/sincronizadas não são cobertos. Não há promessa de durabilidade contra qualquer falha física/queda de energia.
- Os limites HTTP são por operação de conexão/leitura; não são prazo total de toda coleta nem proteção absoluta contra todos os padrões de resposta lenta.
- O limite de 2 MiB e os lotes de até 24 meses continuam. A exportação CLI usa publicação atômica por hard link; o navegador usa bytes preparados sem reconsulta no clique.

Referências primárias: [HTTPX — interface e opções de requisição](https://www.python-httpx.org/api/), [DuckDB — concorrência](https://www.duckdb.org/docs/current/connect/concurrency), [Streamlit — download_button](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button), [OWASP — CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection).

[Guia regional](AREAS.md) · [Arquitetura](ARQUITETURA.md) · [Validação 0.5.0](VALIDACAO-0.5.0.md).
