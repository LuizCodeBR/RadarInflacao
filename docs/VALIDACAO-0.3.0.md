# Validação — Radar da Inflação 0.3.0

16/11/2026, horário de São Paulo. Implementação e evidências em D:/Projetos/RadarInflacao, sem recursos pagos.

## Testes automatizados

- Python 3.13.14 / Windows, testar.cmd: **178 aprovados**, 76,43 s; Ruff aprovado.
- Python 3.12.13 / Windows: **178 aprovados**, 80,03 s.
- 34 casos novos dos grupos, além dos 144 da versão 0.2.1.
- Metadados alterados, categorias ausentes/duplicadas/desconhecidas, localidade indevida, unidade incorreta, meses/valores ausentes e pesos inconsistentes.
- Ausência estrutural em 12 meses de janeiro–novembro/2020, sem conversão para zero.
- Importação repetida, revisão incremental de 216 registros, falha de validação e rollback de gravação parcial preservando ambos os conjuntos.
- Filtros, ranking, isolamento entre grupos, comparação, CSV/procedência e texto inválido recusado.
- Migração de um banco com esquema 1 e registro nacional preservado para esquema 2.
- Outro processo mantendo atualização não concluída: nova consulta bloqueada, snapshot antigo preservado, novo snapshot com valores publicados após COMMIT.
- Interface offline, seleção vazia, ausência histórica, referência sem cobertura e downloads sem rerun.
- Resultado parcial da atualização geral/grupos sem alegar sucesso integral.
- Todos os testes anteriores de segurança, precisão decimal e exportação concorrente continuam aprovados.

As contagens não representam percentual de cobertura ou auditoria externa. Tempos são observações destas execuções, sem comparação de desempenho entre versões do Python.

## Fonte e amostra real

Tabela 7060, Brasil, nove grupos, quatro medidas: 82 meses, janeiro/2020–outubro/2026, 738 registros. Resposta original com 57753 bytes e 99 campos de 12 meses estruturalmente ausentes.

SHA-256 da resposta:
f8ab47471964e4510cb0b45ad72e1cd01a18719b8647b2e833d53ffff07260a4

URLs, data e hash dos metadados estão em sample/groups/manifest.json. A amostra nacional anterior foi preservada.

Coletas reais em base de ensaio .cache/coleta-grupos030:

- Importação: 738 inseridos.
- Reconferência completa online: 738 sem alteração, zero duplicações, mesmo hash da amostra.
- Reconferência incremental: novembro/2024–outubro/2026, 216 sem alteração, total 738 preservado.
- Hash incremental: 3c0430cae890406e460c1814b6296020989b293610d566d16ac682d969807ead.

## Navegador e distribuição

A verificação no navegador usa Chromium já disponível no D:, servidor local em porta temporária e base separada .cache/browser030. Não é dependência para executar o projeto.

A interface mantém o modo nacional e acrescenta Grupos de despesas. São verificados os nove grupos, três gráficos, ranking, comparação anual, os três downloads, campo vazio no CSV histórico e largura mobile emulada. Verificação final aprovada: nove grupos, três gráficos, ranking, referência anual, três CSVs com contagens e dados conferidos, campo histórico vazio e largura mobile sem transbordamento. Capturas desktop/mobile conferidas visualmente.

A conferência visual identificou ordem de barras diferente da tabela durante mudanças da seleção. Corrigido com ordenação explícita no gráfico e teste de regressão. Legendas foram reorganizadas e a altura do gráfico ajustada ao número de grupos.

A base local data/ foi migrada, com cópia anterior em .cache/antes-migracao030. Os 82 registros nacionais permaneceram idênticos; 738 registros dos grupos foram importados.

Após o encerramento do navegador houve registro de conexão reiniciada pelo cliente no transporte do Streamlit/Windows (WinError 10054). Os fluxos verificados e os arquivos baixados concluíram; não houve perda de dados observada.

O ZIP inclui módulos novos e sample/groups. Cópia separada sem ambiente em .cache/validacao030/RadarInflacao: preparar.cmd criou venv e instalou o projeto usando uv já disponível; importação das duas amostras, exportação de seis registros e painel dos grupos via AppTest aprovados. O caminho convencional pip permanece disponível e foi validado na versão 0.2.0; não foi repetido nesta etapa.

O ZIP extraído é conferido quanto a integridade das amostras, versão, importação, CSV e análise dos grupos. O conjunto de pacotes instalado permanece o mesmo, com Python 3.12/3.13. Altair, já instalado pelo Streamlit, passa a ser declarado diretamente porque os gráficos usam sua API.

## Limites

Windows executado; Linux/macOS nativos e celular físico não foram testados nesta etapa. Workflow para Windows/Linux preparado, sem execução remota. Nenhum serviço foi publicado ou contratado.

O indicador é nacional, não representa a inflação pessoal. O ranking ordena variações mensais dos grupos escolhidos; não calcula contribuição ao IPCA. A atualização dos dois conjuntos é transacional por conjunto e pode ter sucesso parcial, identificado na interface/CLI.

O acesso concorrente exige o protocolo de bloqueio da aplicação e um disco local. Limites da publicação de CSV e da proteção contra fórmulas permanecem descritos na [revisão 0.2.1](REVISAO-0.2.1.md).
