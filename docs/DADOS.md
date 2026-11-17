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

Até a versão 0.3.1, o banco preservava histórico de execução e arquivos brutos, sem eventos de antes/depois por campo. A partir da 0.4.0, mudanças detectadas são registradas prospectivamente na central, sem garantia de imutabilidade contra edição externa. Respostas brutas validadas permitem inspecionar lotes anteriores; o banco analítico representa a última versão publicada de cada mês. Arquivos alterados no disco não são automaticamente reparados.

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


## Segunda tabela: grupos do IPCA

Na versão 0.3.0, tabela 7060 com Brasil/N1/1, classificação 315 e nove grupos fixos de nível 1. Variáveis 63/69/2265/66, unidade %. sample/groups guarda 738 registros (82 meses), com manifesto e hashes independentes da amostra nacional.

Os 99 campos ausentes são exclusivamente os acumulados em 12 meses dos nove grupos de janeiro a novembro/2020. Preservados como NULL; CSV vazio, tela Não disponível. Ausência fora dessa regra é erro. A API pode retornar unidade vazia no corpo da variável 2265 nesse intervalo; metadados % e a janela histórica são conferidos.

Pesos são validados entre 0 e 100, soma por mês com tolerância de 0,05 p.p. Os rankings são de variação, sem confundir taxa com contribuição. Consulte [grupos e interpretação](GRUPOS.md).


## Qualidade e histórico — 0.4.0

A central verifica o estado local e registra operações de atualização. O histórico de mudanças inicia na migração: observações já existentes continuam iguais e não recebem alterações retroativas inventadas. Na primeira importação de uma base vazia, os campos são inclusões. Na reconferência idêntica, só a procedência e a tentativa são atualizadas.

Um hash identifica uma resposta arquivada, mas não é assinatura de autenticidade do IBGE nem proteção contra alguém com escrita em todo o disco. Uma mudança detectada entre coletas não é automaticamente classificada como revisão oficial. O IPCA tem política de não revisão rotineira; correções excepcionais ou divergências devem ser investigadas em sua fonte.

CSV de histórico distingue inclusão e alteração, valores anteriores/novos, grupo, mês, indicador, modo, momento e IDs/hash. CSV de qualidade registra oito verificações (quatro por conjunto) e o contexto operacional/temporal. Na simulação, o modo é identificado nos dois relatórios; valores artificiais não se tornam dados oficiais.

A indicação de disponibilidade depende dos metadados válidos efetivamente observados. Amostra informa sua data original; consulta online informa a data da verificação; ausência de metadados registrados é Não verificado. Abrir a central ou mudar de mês no calendário não dispara consulta ao IBGE. [Guia da central](QUALIDADE.md).

## Áreas a partir de 0.5.0

A amostra em sample/areas preserva 82 meses × 17 localidades (16 áreas e Brasil), 1394 registros e 187 ausências históricas de 12 meses. Origem 7060/315/7169; três medidas oficiais. As respostas são preservadas em pacote com corpo, URL e hash de cada lote de até 24 meses. A referência brasileira acompanha o lote regional, sem recalcular média de localidades. [Abrangência, métodos, precisão e limites](AREAS.md).

## INPC nacional — versão 0.6.0

Fonte tabela 1736, Brasil/N1, variáveis 44/68/2292 (%). Amostra em sample/inpc: 82 meses, janeiro/2020–outubro/2026, sem ausências nas três medidas. Manifesto com URLs, data e hashes. Os originais das outras amostras permanecem.

IPCA comparado é o nacional da tabela 1737. A diferença sempre é INPC − IPCA. Cada índice mantém publicação, coleta e procedência próprias; o alinhamento exige todos os meses solicitados, sem imputação. [Método e limites](INDICES.md).
