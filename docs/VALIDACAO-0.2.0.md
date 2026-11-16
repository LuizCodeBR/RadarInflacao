# Validação — Radar da Inflação 0.2.0

16/11/2026, horário de São Paulo. Comparações, explicações e exportação implementadas em D:/Projetos/RadarInflacao. Sem conta, recurso pago, publicação externa ou tarefa agendada.

## Resultados executados

| Verificação | Resultado |
| --- | --- |
| Windows / Python 3.13.14, iniciador testar.cmd | 92 aprovados, zero falhas, 27,77 s |
| Windows / Python 3.12.13, ambiente separado | 92 aprovados, zero falhas, 16,56 s |
| Cópia limpa / venv + pip / Python 3.13.14 | 92 aprovados, zero falhas, 9,41 s |
| Ruff | Aprovado |
| Navegador real / Chromium | Comparações, explicações, download CSV e layout aprovados |
| Mobile emulado / 412 px | Página sem transbordamento horizontal; tabela com rolagem interna |
| Dependências e banco | Mesmas dependências da 0.1.0; esquema 1 preservado |

Os tempos são apenas os observados nestas execuções, sem comparação de desempenho entre versões do Python. As contagens não são uma medida percentual de cobertura.

## Casos automatizados

- 34 casos de análise: composição em vez de soma, zero, deflação, mês único, fator zero, precisão decimal independente do chamador, ordem das linhas sem mutação, janelas entre anos, parâmetros inválidos, meses ausentes/duplicados, valores inválidos, sinal da diferença, sobreposição, durações diferentes, períodos idênticos e arredondamento sem zero negativo.
- 6 testes da interface: importação/filtros, falha da fonte com base preservada, comparação anual e explicações contextualizadas, referência sem cobertura, comparação manual com avisos e filtros que não consultam a rede nem alteram o snapshot.
- 8 testes CLI/CSV: casos anteriores preservados e novos casos para janelas, métodos, pontos percentuais, BOM/CRLF e precisão da comparação além do contexto decimal padrão.
- 27 testes de contrato, 9 de pipeline/persistência/concorrência e 8 de cliente HTTP continuam aprovados.

Total: 92 casos, sendo 40 novos em relação aos 52 da versão 0.1.0.

Os testes usam a amostra e respostas controladas. Não dependem da disponibilidade da API ou de um serviço pago. A procedência e as validações da versão inicial continuam documentadas em [validação 0.1.0](VALIDACAO-0.1.0.md).

## Instalação limpa

Fonte copiada sem ambiente, banco ou caches para D:/Projetos/RadarInflacao/.cache/validacao-020/RadarInflacao.

Executados preparar.cmd -Python com Python 3.13 gerenciado no D: e -UsarPip, depois testar.cmd -UsarPip. A cópia criou seu próprio venv, instalou os requisitos fixados e aprovou Ruff e os 92 testes. Isso verifica o procedimento convencional com pip, sem exigir uv no computador de quem baixar.

## Verificação no navegador

Servidor local na porta 8503, dados de ensaio separados em .cache/browser-020. Navegador e cache de testes já disponíveis no D: foram reutilizados; não são requisitos do aplicativo.

Verificados:

1. A = janeiro–março/2024 e referência anterior = outubro–dezembro/2023.
2. Referência anual = janeiro–março/2023; estimativa de A exibida em 1,42%.
3. CSV baixado pelo botão real, BOM e valor calculado 1,4154915776% preservados.
4. Explicações abertas e exemplo de composição de dois meses de 1%.
5. Intervalo manual com durações diferentes e sobreposição, com avisos.
6. Intervalo B invertido, sem retirar o gráfico nem as medidas oficiais de A.
7. Tela de 412 pixels, botão de exportação acessível e tabela com rolagem própria.
8. Capturas desktop/mobile e detalhe da comparação, conferidas visualmente.

As capturas usam a amostra identificada. Não houve nova coleta real nesta etapa; a função de coleta e seus testes de regressão foram preservados.

## Limites da validação

Execução nativa realizada no Windows. Os iniciadores Linux/macOS permanecem disponíveis, com a verificação de sintaxe da versão inicial; não há alegação de execução nativa nesses sistemas nesta etapa. O workflow para Windows/Linux × Python 3.12/3.13 está preparado, mas não foi executado remotamente.

Não houve teste em celular físico, publicação de site ou criação de aplicativo nativo. As comparações usam uma única leitura da base; o arquivo local e o protocolo de bloqueio continuam com os limites descritos na [arquitetura](ARQUITETURA.md).

O acumulado de um intervalo é identificado como estimativa por usar taxas mensais já arredondadas. Medidas oficiais no ano/em 12 meses e a procedência por mês são preservadas.
