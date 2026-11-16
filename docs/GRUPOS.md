# Análise dos nove grupos — versão 0.3.0

## Usar o painel

Execute iniciar.cmd e escolha Grupos de despesas em Análise. A seleção inicial destaca Alimentação e bebidas, Habitação e Transportes; todos os nove grupos estão disponíveis no seletor.

Escolha início/fim do período A e o indicador do gráfico: mensal, no ano ou em 12 meses. O ranking tem um seletor de mês dentro de A e ordena os grupos selecionados da maior para a menor variação mensal. Empates seguem a ordem oficial dos grupos.

A comparação B oferece período anterior de mesma duração, mesmo intervalo do ano anterior ou datas manuais. Exibe gráfico de acumulados estimados A/B, tabela com as quatro medidas e diferenças em pontos percentuais. Períodos de durações diferentes ou sobrepostos têm aviso. Falta de cobertura não encurta a janela.

Há três downloads independentes: dados do período/grupos escolhidos, ranking do mês e comparação A/B. Todos usam o snapshot da tela, sem nova consulta ao clicar.

## Fonte e significado

[IBGE/SIDRA 7060](https://sidra.ibge.gov.br/tabela/7060), Brasil/N1/1, classificação 315, categorias de nível 1. [Metadados](https://servicodados.ibge.gov.br/api/v3/agregados/7060/metadados).

| ID | Grupo |
| --- | --- |
| 7170 | Alimentação e bebidas |
| 7445 | Habitação |
| 7486 | Artigos de residência |
| 7558 | Vestuário |
| 7625 | Transportes |
| 7660 | Saúde e cuidados pessoais |
| 7712 | Despesas pessoais |
| 7766 | Educação |
| 7786 | Comunicação |

Variáveis: 63 mensal; 69 no ano; 2265 em 12 meses; 66 peso mensal. Unidade: %. O acumulado no ano começa em janeiro; o de 12 meses cobre o mês da observação e os 11 anteriores. O filtro não redefine os valores oficiais.

Peso é participação na composição do índice naquele mês. O ranking é de taxas, não de contribuição em pontos percentuais. Pesos não são somados ao longo do tempo e não há cálculo de contribuição nesta versão.

A estimativa do intervalo multiplica fatores mensais, com precisão decimal local. Como usa taxas publicadas já arredondadas, pode diferir do acumulado oficial. Diferença = A menos B, em p.p.; não há anualização.

## Ausência histórica explícita

Na resposta oficial obtida, janeiro–novembro/2020 têm ... para os acumulados de 12 meses dos nove grupos: 99 campos ausentes em 738 registros. As taxas mensais, no ano e os pesos continuam presentes.

Essa ausência específica é aceita como NULL, apresentada como Não disponível e exportada como campo vazio. Uma comparação cujo último mês não tenha esse indicador deixa também a diferença vazia. Não há substituição por zero nem tentativa de reconstruir o acumulado oficial.

A API omite a unidade no corpo da variável 2265 quando o intervalo inclui esses meses; essa exceção é aceita somente nessa variável/janela e com metadados % validados. Falta de mensal, peso ou ausência de 12 meses fora desse intervalo é erro.

## Coleta e procedência

A amostra em sample/groups contém resposta original, metadados e manifesto com URLs, instante UTC e hashes. Foram coletados 82 meses, janeiro/2020–outubro/2026: 738 registros e quatro medidas por registro, com as ausências identificadas.

Toda coleta valida Brasil, categorias e nomes esperados, quatro variáveis sem duplicação, meses contínuos, taxas finitas e pesos de 0 a 100. A soma dos nove pesos por mês deve ficar a até 0,05 ponto percentual de 100, acomodando o arredondamento da fonte.

Grupos têm histórico de execuções e procedência próprios, inclusive modo amostra/consulta por registro. O painel pode identificar base mista. A atualização reconfere os últimos 24 meses existentes e busca os novos; --full reconfere desde 2020. A amostra não substitui dados já consultados.

## Banco e migração

O esquema passa de 1 para 2. A migração transacional acrescenta group_dimension, group_ingestion e group_observation, sem reescrever os registros do índice geral. A chave dos grupos é mês + grupo. As quatro medidas são DECIMAL(14,6), com 12 meses anulável para a ausência histórica.

O mesmo bloqueio entre processos coordena ambos os conjuntos. Um snapshot do painel pode ler índice geral, grupos e históricos sob um único acesso. Os resultados preparados ficam em memória na sessão e não mudam por uma coleta posterior.

Cada conjunto é publicado em sua própria transação. Atualizar ambos pode ter sucesso parcial: a interface identifica erros por conjunto; a CLI retorna status PARTIAL e código 2, com sucessos e erros discriminados. Não há promessa de transação única envolvendo as duas fontes.

Versões antigas do aplicativo recusam esquema 2. Para voltar ao código antigo seria necessário restaurar uma cópia compatível do banco, com o aplicativo encerrado.

## Comandos

Os iniciadores continuam iguais: iniciar.cmd, testar.cmd, atualizar.cmd e atualizar.cmd -Completo. Em Linux/macOS: bash iniciar.sh, bash testar.sh e bash atualizar.sh [--full].

Demonstração e atualização pela CLI atendem aos dois conjuntos por padrão:

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao demo
.\.venv\Scripts\python.exe -m radar_inflacao update
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset groups
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset national --full
~~~

Exportar apenas os grupos escolhidos:

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao export --dataset groups --groups 7170 7625 --from 2024-01 --to 2024-03 --output exports\grupos.csv
~~~

Sem --groups, todos os nove são selecionados. O CSV preserva números, IDs, nomes canônicos, peso, modo, data, hash e coleta. Exportação nacional continua sendo o padrão do comando export. A publicação pela CLI mantém a proteção contra sobrescrita e exige volume com suporte a hard links; o download no navegador não tem esse requisito.

Não há novas dependências, contas, nuvem, cobrança ou atualização automática. A primeira instalação precisa de internet; depois as duas amostras permitem explorar o painel offline. Consultar atualizações exige conexão com o IBGE.
