# Comparações e explicações — versão 0.2.1

## Escolher os períodos

O filtro principal define A. Em Comparar com:

- Período anterior de mesma duração: janeiro–março/2024 compara com outubro–dezembro/2023.
- Mesmo período do ano anterior: janeiro–março/2024 compara com janeiro–março/2023.
- Escolher outro período: permite selecionar início e fim de B entre os meses disponíveis.

As datas são inclusivas. A base precisa cobrir todos os meses dos dois intervalos, sem repetição. A janela não é encurtada silenciosamente quando falta cobertura. Uma comparação indisponível não impede consultar gráfico, tabela ou CSV mensal de A.

## O que cada resultado significa

| Resultado | Janela e origem |
| --- | --- |
| Variação mensal | Valor oficial do último mês em relação ao anterior |
| Acumulado no ano | Valor oficial desde janeiro até o último mês |
| Acumulado em 12 meses | Valor oficial do último mês e dos 11 anteriores |
| Acumulado estimado no período | Composição local das taxas mensais de todos os meses selecionados |

Os indicadores oficiais não passam a cobrir somente o filtro. Por exemplo, selecionar fevereiro–março/2024 mantém o acumulado no ano de março cobrindo janeiro–março/2024, e o acumulado em 12 meses cobre abril/2023–março/2024. Esta última janela pode começar antes da cobertura local: o indicador oficial já vem da fonte.

O acumulado estimado usa:

~~~text
fator = produto de (1 + taxa_mensal / 100)
acumulado_estimado = (fator - 1) × 100
~~~

Dois meses de 1% dão 2,01%. Um mês de -1% seguido por um mês de +1% resulta em -0,01%. A composição não é uma soma ou média das taxas.

As taxas publicadas já estão arredondadas. Por isso, sua composição é uma estimativa e pode divergir do acumulado oficial calculado com números-índice. Não substitui as duas séries acumuladas do IBGE.

## Interpretar a comparação

A diferença é sempre A menos B em pontos percentuais (p.p.). Se A = 3% e B = 2%, a diferença é +1,00 p.p. Não há divisão por B, inclusive quando B é zero ou negativo.

As diferenças usam valores anteriores ao arredondamento. A tela mostra duas casas com arredondamento decimal ROUND_HALF_UP; por isso, a diferença pode não coincidir com a subtração dos dois valores já arredondados exibidos. O zero negativo é apresentado como zero.

Avisos:

- Durações diferentes: a quantidade de meses aparece, e os resultados não são anualizados.
- Sobreposição: meses comuns participam dos dois cálculos; não são duas janelas independentes.
- Intervalos idênticos: diferenças iguais a zero.
- Cobertura insuficiente ou intervalo invertido: a comparação não é produzida.

Uma inflação positiva mais baixa indica preços aumentando mais devagar; por si só, não indica redução do nível de preços. Taxa mensal negativa representa deflação naquele mês. O IPCA nacional não representa necessariamente a inflação pessoal.

## Exportar

Baixar CSV da comparação gera quatro linhas: estimativa do intervalo e três medidas oficiais do último mês. Registra indicador, datas A/B, quantidades de meses, valores, diferenças, método e fonte.

O download utiliza os dados já exibidos, mesmo se outra sessão atualizar a base. Atualize a página para incorporar uma coleta posterior.

O arquivo usa UTF-8 com BOM, ponto e vírgula, vírgula decimal e quebras CRLF. Os números preservam a precisão do cálculo, sem o arredondamento de duas casas da tela. A procedência por mês continua disponível no CSV original do período, que mantém seu formato.

## Executar e verificar

Não há instalação adicional. Use iniciar.cmd e testar.cmd na pasta do projeto; em Linux/macOS, bash iniciar.sh e bash testar.sh. As comparações funcionam sobre a amostra local, sem API ou serviço pago.

Funções de cálculo: src/radar_inflacao/analysis.py. Exportação: src/radar_inflacao/report.py. Integração: app.py. Testes: tests/test_analysis.py, tests/test_app.py e tests/test_cli_report.py.

## Referências oficiais

- [IBGE: inflação, conceitos e metodologia com números-índice](https://www.ibge.gov.br/explica/inflacao.php).
- [Banco Central: composição de índices mensais](https://www4.bcb.gov.br/pec/correcao/metodologiaInd.asp?frame=1).
- [IBGE/SIDRA: tabela 1737](https://sidra.ibge.gov.br/tabela/1737).
