# Comparador nacional IPCA × INPC — 0.6.0

## Usar

Execute iniciar.cmd e abra IPCA × INPC em Análise. Escolha mês inicial/final e uma das três medidas. Os dois gráficos e os indicadores usam exatamente o mesmo recorte: evolução de IPCA/INPC e diferença INPC − IPCA. A tabela inclui as três medidas e três diferenças. Os downloads usam bytes do retrato mostrado, sem nova leitura no clique. Após alterar um filtro, aguarde o Período aplicado aos índices mostrar o recorte desejado antes de baixar.

Na seção de períodos, compare A com o intervalo anterior de mesma duração, com o ano anterior ou com B manual. Há aviso de sobreposição e durações diferentes. Um B indisponível não remove a consulta válida de A nem seu CSV. Um A inválido impede gráficos/downloads. Tabelas largas têm rolagem horizontal no celular.

## Interpretação

IPCA: famílias com renda de 1 a 40 salários mínimos, qualquer que seja a fonte. INPC: famílias com renda de 1 a 5 salários mínimos, cuja pessoa de referência é assalariada. São populações/cestas/pesos distintos; a comparação não mede a inflação de uma pessoa específica nem identifica causalidade.

Diferença sempre = INPC − IPCA, em pontos percentuais. Positiva significa INPC maior. Exemplo fictício: 0,60% − 0,40% = +0,20 p.p. Números negativos válidos continuam numéricos no CSV.

No ano e em 12 meses são os acumulados oficiais encerrados em cada mês. Alterar o início do filtro não os redefine. Na comparação A/B, as medidas oficiais são as do último mês de cada janela. O acumulado do intervalo é uma estimativa pela multiplicação dos fatores mensais publicados, sem soma ou anualização. Pode divergir do acumulado calculado pelo IBGE com números-índice.

Na amostra de outubro/2026: IPCA mensal 0,14%, INPC 0,22%, diferença +0,08 p.p.; no ano 4,10% e 4,24%, diferença +0,14 p.p.; em 12 meses 4,63% e 4,49%, diferença −0,14 p.p. São os dados incluídos, não uma consulta automática atual.

## Fontes e contratos

| Série | Tabela | Mensal | No ano | 12 meses |
| --- | --- | --- | --- | --- |
| IPCA nacional | 1737 | 63 | 69 | 2265 |
| INPC nacional | 1736 | 44 | 68 | 2292 |

Referências: [tabela 1737](https://sidra.ibge.gov.br/tabela/1737), [tabela 1736](https://sidra.ibge.gov.br/tabela/1736), [metadados INPC](https://servicodados.ibge.gov.br/api/v3/agregados/1736/metadados), [definições IBGE](https://anuario.ibge.gov.br/2024/glossario-2024.html).

A referência brasileira regional continua sendo da 7060 e não participa deste comparador. Não é exigido que índices distintos tenham a mesma coleta: cada série mantém sua própria origem/data/hash. O retrato de ambas é lido sob o mesmo bloqueio local, com as publicações disponíveis naquele momento.

Metadados: ID da tabela, periodicidade mensal, nível N1, IDs/unidades próprias e fim válido. Dados: exatamente três variáveis, Brasil/N1, unidade %, classificação vazia, meses esperados sem lacunas, duplicações ou extras; decimal finito em faixa limitada. Ausências são recusadas, inclusive em 12 meses desde 2020 na tabela 1736. JSON tem limite 2 MiB e chaves duplicadas recusadas. Fonte HTTPS fixa, sem redirecionamento, timeout e retries limitados.

Na leitura analítica são revalidados valores, mês/dia, UUID, modo/data/hash, sucesso/finalização da publicação, janela da coleta e URL exata da série. Uma troca IPCA/INPC ou registro inválido em B também é recusado. O cálculo usa Decimal e contexto próprio, sem depender da precisão/traps globais. A tela mostra duas casas; o CSV conserva o cálculo.

## Cobertura e atualização

Amostra INPC em sample/inpc: janeiro/2020–outubro/2026, 82 registros, três medidas obrigatórias; dados reais coletados do IBGE. O manifesto preserva URL, data com fuso e hashes dos dados/metadados. Ambiente preparado permite usar a amostra offline. A primeira abertura importa apenas o INPC faltante; não consulta a rede nem substitui dados live.

Os filtros mostram a união dos meses das bases, com cobertura de cada índice explícita. Se as coberturas diferirem, há aviso. A aplicação exige que ambos cubram todo A e todo B solicitado; não preenche zero, não imputa e não reduz silenciosamente a janela.

Atualizar pelo IBGE, atualizar.cmd e demo/update sem --dataset incluem quatro conjuntos. Cada conjunto publica sua própria transação e pode falhar independentemente; resultados parciais são informados. INPC incremental revisita 24 meses e busca meses novos; --full reconfere desde 2020. Atualizar apenas INPC não faz o IPCA parecer recém-consultado.

## Exportações

- CSV IPCA × INPC: uma linha por mês, seis taxas, três diferenças INPC − IPCA e procedência de ambos (modo, data, SHA-256, coleta), mais fontes 1737/1736.
- CSV A/B: quatro linhas (estimativa do intervalo e três medidas oficiais), janelas/quantidades de meses, IPCA/INPC em A/B, diferença entre índices em cada janela e A − B de cada índice. Método/fontes identificados; procedência por mês fica no CSV do período.
- CLI também exporta INPC isoladamente. CSV da qualidade passa a ter dezesseis linhas; histórico aceita --dataset inpc. Formato das colunas do histórico permanece.

UTF-8 com BOM, ponto e vírgula, CRLF e vírgula decimal. Textos canônicos e procedência são validados antes de serializar. Publicação CLI é atômica, sem sobrescrever um arquivo existente, inclusive em corrida entre processos. Requer volume local com hard links nessa rota; download do navegador não exige esse suporte.

## CLI

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao demo --dataset inpc
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset inpc
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset inpc --full
.\.venv\Scripts\python.exe -m radar_inflacao export --dataset inpc --from 2024-01 --to 2024-03 --output exports\inpc.csv
.\.venv\Scripts\python.exe -m radar_inflacao export --dataset indices --from 2024-01 --to 2024-03 --output exports\indices.csv
.\.venv\Scripts\python.exe -m radar_inflacao compare-indices --from 2024-01 --to 2024-03 --from-b 2023-01 --to-b 2023-03 --output exports\indices-ab.csv
.\.venv\Scripts\python.exe -m radar_inflacao quality-export --report changes --dataset inpc --kind ADDED --output exports\historico-inpc.csv
~~~

--data-dir continua disponível antes do comando. Omitir meses na exportação do comparador usa a extensão das duas bases e exige cobertura completa de ambas. Não escolhe silenciosamente uma interseção menor.

## Banco e instalação

Migração 4→5 adiciona inpc_ingestion, inpc_observation, inpc_change e o início do histórico INPC. As tabelas anteriores permanecem. A primeira importação cria 246 inclusões por campo (82 × 3); reconferências iguais não criam eventos. Dados, mudanças e sucesso são confirmados juntos. Interrupção antes do commit desfaz a publicação e a próxima abertura marca a tentativa INTERRUPTED.

Encerre o painel e preserve data antes de atualizar outra instalação. Código até 0.5.1 não abre esquema 5; reversão exige cópia anterior compatível. Nesta máquina, a cópia prévia está em D:/Projetos/RadarInflacao/.cache/antes-migracao060. Não é backup automático.

Python 3.12/3.13 e dependências existentes. Nenhuma extensão do VS Code, Node, Docker, banco servidor, API paga ou conta nova é necessária. Use o pacote fonte completo para receber app, amostras e iniciadores. O wheel isolado não distribui esses recursos.

[Instalação](INSTALACAO.md) · [Arquitetura](ARQUITETURA.md) · [Validação](VALIDACAO-0.6.0.md).
