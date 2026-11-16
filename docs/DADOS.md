# Fonte, amostra e qualidade

Fonte oficial: [IBGE, API de dados agregados](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3), tabela [1737](https://sidra.ibge.gov.br/tabela/1737), território Brasil (N1/1). Variáveis 63, 69 e 2265, todas em %. Metadados e resposta pública estão preservados em sample/.

sample/manifest.json registra origem, URL completa, instante UTC da obtenção, período e SHA-256 dos dois arquivos. A amostra desta entrega contém 82 meses, janeiro/2020 a outubro/2026. É uma cópia dos dados publicados, com fonte identificada; o projeto não é um produto oficial do IBGE.

- monthly: variação do mês.
- year_to_date: acumulado no ano civil até aquele mês.
- twelve_month: acumulado dos 12 meses até aquele mês.

Os acumulados são oficiais e não somas das taxas mensais. O filtro não redefine essas janelas. Exemplo da fonte: janeiro/2024 tem 0,42% mensal, 0,42% no ano e 4,51% em 12 meses.

## Contrato validado

Tabela e metadados esperados, frequência mensal, nível nacional, variáveis distintas, unidade %, uma série por medida, ausência de classificações inesperadas, mesmos meses nas três medidas e cobertura contínua. JSON com chaves repetidas, corpo inválido, valor ausente, NaN, unidade diferente ou localidade inesperada falham integralmente.

Valores decimais têm até seis casas e faixa técnica entre -100 e 999999,999999. Esse limite protege a representação e não funciona como uma análise de plausibilidade econômica. Zero e taxas negativas válidas são conservados.

## Procedência

Cada mês aponta para a última coleta que o conferiu. O CSV inclui modo, momento, hash e ID da coleta. A origem do mês pode ser amostra ou consulta; uma base pode misturar ambos. A atualização completa permite reconferir todo o período pela API.

Histórico de execução não é uma promessa de histórico imutável de todos os valores revisados. Respostas brutas validadas permitem inspecionar lotes anteriores; o banco analítico representa a última versão publicada de cada mês. Arquivos alterados no disco não são automaticamente reparados.

A disponibilidade do IBGE pode mudar. Falhas não são convertidas silenciosamente em sucesso com a amostra. A atualização pede nova tentativa e preserva os dados publicados anteriormente.

## Comparações e precisão

A partir da versão 0.2.0, o acumulado estimado de um intervalo é:

~~~text
[(1 + taxa_1 / 100) × ... × (1 + taxa_n / 100) - 1] × 100
~~~

O primeiro e o último mês são incluídos. Dois meses de 1% produzem 2,01%; um mês negativo é preservado. Não se somam taxas, não se calcula média como acumulado e não se anualizam intervalos de tamanhos diferentes.

A composição utiliza as taxas mensais publicadas. Elas têm arredondamento e podem produzir resultado diferente da variação oficial obtida com números-índice. As medidas oficiais no ano e em 12 meses continuam sendo os valores do IBGE do último mês de cada janela.

Metodologia de composição: [Banco Central, índices de preços](https://www4.bcb.gov.br/pec/correcao/metodologiaInd.asp?frame=1). Metodologia por números-índice e conceitos: [IBGE, inflação](https://www.ibge.gov.br/explica/inflacao.php).

A diferença é taxa A menos taxa B, em pontos percentuais, antes do arredondamento da tela. Uma inflação positiva menor significa aumento mais lento do nível de preços, sem implicar queda de preços. A cobertura nacional não descreve a cesta individual de uma pessoa.

Veja [comparações e exemplos](COMPARACOES.md) para as janelas automáticas, avisos e exportação.
