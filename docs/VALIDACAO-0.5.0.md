# Validação — Radar da Inflação 0.5.0

16/11/2026. Comparação do índice geral do IPCA entre as 16 áreas e Brasil, com gráficos, ranking, diferenças em pontos percentuais, comparação A/B, três CSVs, amostra offline, central e esquema 4. Trabalho no D:, sem serviços pagos ou novas dependências.

## Testes

- Windows / Python 3.13.14, testar.cmd: **371 aprovados**, 299,23 s; Ruff aprovado.
- Windows / Python 3.12.13: **371 aprovados**, 296,90 s.
- 55 casos regionais novos, além dos 316 anteriores. As suítes completas rodaram simultaneamente com bases temporárias distintas; os tempos não são comparação de desempenho.
- Rodada inicial regional: 47 aprovados; depois foram incluídos mais oito casos de migração, falha e concorrência. Uma rodada intermediária encontrou importação ausente de BusyError no teste de processos, corrigida antes das suítes completas.
- A rodada inicial de compatibilidade sinalizou expectativas do esquema 3 e dos dois conjuntos antigos, atualizadas para esquema 4/três conjuntos. Todos os cenários passaram nas suítes finais.

Os 55 casos novos em tests/test_areas.py cobrem contratos/respostas/pacote, origem, janela de requisição, falhas, importação idempotente, coleta incremental e histórico, rollback, migração e falha de migração, precisão sob contexto decimal restritivo, empates, seleção de áreas, ausência histórica e referência brasileira, proteção CSV, filtros da qualidade, CLI e interface.

A suíte anterior foi preservada. Expectativas de esquema e número de verificações da central foram atualizadas: esquema 4 e terceiro conjunto regional. Bases antigas simuladas nos testes de migração não incluem tabelas regionais. Esses ajustes não removem os cenários de segurança/concorrência anteriores.

## Fonte real e amostra

API pública do IBGE 7060, metadados e três medidas do índice geral para 17 localidades. Quatro requisições de observações, cada uma de até 24 meses. 1394 registros de janeiro/2020 a outubro/2026, com 187 ausências conhecidas em 12 meses. A validação identificou as duas grafias da fonte para UF e permite somente os formatos conhecidos, mantendo chave composta por nível e código.

sample/areas/manifest.json registra data, URLs e hashes. ibge-7060.json é um pacote de 117058 bytes com os corpos originais e seus hashes. Metadados e pacote são verificados antes da importação. Um endpoint auxiliar de localidades N7 retornou lista vazia; o catálogo foi confirmado na resposta efetiva de observações com N7 e N6 explícitos, não inferido da lista vazia.

Atualização real em .cache/areas-real050, separada da base principal: amostra inicial 1394; incremental novembro/2024–outubro/2026 = 408 registros sem mudança; reconferência completa = 1394 sem mudança. Zero alterações de valor e duplicações; qualidade regional OK. Log .cache/coleta-real050.log.

## Concorrência

O pipeline regional real roda em outro processo, pausado dentro da transação depois da escrita. Nova leitura recebe BusyError. O CSV de valores e o CSV de histórico já preparados mantêm seus bytes. Commit confirma valores e evento juntos; encerramento forçado desfaz ambos e deixa a tentativa para INTERRUPTED. Os testes anteriores equivalentes dos grupos e índice nacional permanecem na suíte.

Não se declara suporte a pasta sincronizada/rede, programas externos que ignorem o bloqueio ou múltiplos servidores. Cada conjunto tem transação independente; a publicação das 16 áreas e Brasil é conjunta dentro do conjunto regional.

## Migração da instalação principal

Sob o bloqueio local, radar.duckdb e WAL se existente foram copiados para .cache/antes-migracao050 antes de abrir a migração. Cada tabela anterior foi serializada no SQL e comparada antes/depois; o novo registro de início do histórico regional foi excluído apenas dessa comparação de audit_baseline.

Resultado: esquema 3→4, observações, tentativas e eventos anteriores preservados. Nacional 82 e grupos 738 permanecem iguais. A amostra regional foi então importada, com 1394 registros e 4182 inclusões por campo. As áreas principais estão em modo sample; os ensaios de atualização real usaram outra base. Log .cache/migracao050.log. Essa cópia é uma proteção desta migração, sem agendamento de backup.

## Navegador e distribuição

Chromium local em 127.0.0.1:8508, base de ensaio .cache/browser050. Desktop 1440×1900 e mobile emulado 412×2200. Gráfico, ranking, três downloads, filtros para janeiro–março/2024, intervalo invertido sem download e ausência de transbordamento da página conferidos. Capturas inspecionadas em docs/imagens/areas-*.png.

A primeira automação mudou de seção antes do fim da preparação inicial e recebeu BusyError; o roteiro passou a aguardar a tela pronta. Outra tentativa precisou abrir explicitamente o seletor antes de digitar o mês. A execução final passou sem alteração de produto para esses casos. Log .cache/navegador050-final.log.

Preparação limpa em .cache/validacao050/RadarInflacao, com preparar.cmd e Python 3.13 no D:. Ambiente novo, mesmas dependências fixadas. Importação e reimportação dos três conjuntos: 82 nacionais, 738 grupos e 1394 regionais; 7380 inclusões sem duplicações. CSV regional filtrado com seis linhas, central com doze verificações, tela regional com três downloads e central via AppTest aprovados. Logs .cache/instalacao050.log e instalacao050-smoke.log.

O ZIP fonte exclui banco, ambiente, caches e exportações pessoais; inclui código, testes, amostras e documentação. Entrega em D:/Projetos/Entregas/RadarInflacao-0.5.0/RadarInflacao-0.5.0-fonte.zip. O pacote extraído é verificado com seu próprio código, importações e CSVs. Evidência .cache/pacote050.log. A rota pip permanece disponível; a preparação limpa desta versão usou uv já instalado, sem adicionar ferramenta ao usuário.

## Limites

Windows e celular emulado; não houve execução nativa Linux/macOS, celular físico ou testes remotos da CI nesta entrega. O workflow inclui Windows/Linux e foi ampliado com comandos regionais. O repositório permanece local, sem remoto configurado.

O índice regional mede variação, não preço absoluto ou custo de vida. A referência nacional é oficial da própria tabela, não uma média simples. Os nove grupos regionais não foram acrescentados. Acumulados de intervalos A/B são estimativas pela composição das taxas publicadas.

Não há agendamento, alerta automático, nuvem ou serviço pago. As amostras continuam funcionando offline após a preparação inicial. O histórico local não é inviolável nem assinado digitalmente.

## Evidências locais

.cache/areas-sample.log, testes050-areas.log, testes050-target2.log, testes050-313.log, testes050-312.log, navegador050-final.log e demais logs da preparação/migração/pacote ficam no D:, ignorados pelo Git.

[Guia regional](AREAS.md) · [Arquitetura](ARQUITETURA.md) · [Revisão anterior](REVISAO-0.4.1.md).
