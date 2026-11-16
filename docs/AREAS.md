# IPCA das 16 áreas e Brasil — 0.5.0

## Usar

Execute iniciar.cmd e abra http://localhost:8501. Em Análise, escolha Comparar áreas. A seção prepara sua amostra regional na primeira abertura. Escolha áreas, mês inicial/final e indicador do gráfico. A seleção padrão é São Paulo, Rio de Janeiro e Brasília; todas as 16 estão disponíveis.

A amostra contém dados reais oficiais de janeiro/2020 a outubro/2026, obtidos em 16/11/2026. São 1394 registros = 82 × 17 (16 áreas e a referência brasileira). Os três campos de cada linha são variação mensal, acumulado no ano e acumulado em 12 meses.

A seção é web local responsiva. Não exige conta, API paga, servidor de banco, Node, Docker ou extensão. A preparação inicial das dependências requer internet; a consulta da amostra funciona offline depois disso.

## Abrangência

| Chave | Área | Recorte identificado na interface |
| --- | --- | --- |
| N7:1501 | Belém - PA | Região metropolitana |
| N7:2301 | Fortaleza - CE | Região metropolitana |
| N7:2601 | Recife - PE | Região metropolitana |
| N7:2901 | Salvador - BA | Região metropolitana |
| N7:3101 | Belo Horizonte - MG | Região metropolitana |
| N7:3201 | Grande Vitória - ES | Região metropolitana |
| N7:3301 | Rio de Janeiro - RJ | Região metropolitana |
| N7:3501 | São Paulo - SP | Região metropolitana |
| N7:4101 | Curitiba - PR | Região metropolitana |
| N7:4301 | Porto Alegre - RS | Região metropolitana |
| N6:1200401 | Rio Branco - AC | Município |
| N6:2111300 | São Luís - MA | Município |
| N6:2800308 | Aracaju - SE | Município |
| N6:5002704 | Campo Grande - MS | Município |
| N6:5208707 | Goiânia - GO | Município |
| N6:5300108 | Brasília - DF | Área pesquisada no Distrito Federal |
| N1:1 | Brasil | Referência oficial |

N7 é denominado Região Metropolitana até 2020 pela API da tabela. O código e o nível são preservados como chave composta; a apresentação identifica a área pesquisada e não faz inferências sobre mudanças administrativas. Brasília usa o identificador N6 fornecido pela fonte, com explicação específica na interface.

Não há cobertura para todas as cidades, para cada estado inteiro ou para as cinco grandes regiões. O Brasil é obtido da própria tabela 7060, não calculado como média simples das taxas locais.

## Gráficos, ranking e diferenças

O gráfico de evolução mostra as áreas selecionadas e o Brasil para a mesma medida. No ano e em 12 meses mantêm suas janelas oficiais; mudar o início do filtro não redefine esses acumulados.

O ranking ordena exclusivamente a taxa mensal de um mês, da maior para a menor, entre as áreas selecionadas. Empates seguem a ordem fixa da tabela de áreas acima. Brasil não recebe posição no ranking. Taxa maior não representa custo de vida maior, preços absolutos mais altos ou maior contribuição para o resultado nacional.

Diferença = valor da área − valor do Brasil, em pontos percentuais, antes do arredondamento. Os cálculos usam Decimal e contexto próprio; a interface exibe duas casas e o CSV conserva os valores calculados.

A tabela 7060 não informa acumulado de 12 meses de janeiro a novembro/2020: são 187 ausências na amostra (11 × 17). Elas ficam Não disponível na tela e vazias no CSV, inclusive nas diferenças correspondentes. Zero é mantido como zero.

A comparação A/B permite intervalo anterior de mesma duração, mesmo intervalo no ano anterior ou escolha manual. O acumulado do intervalo é uma estimativa pela composição das taxas mensais publicadas. Há aviso quando faltam meses, as durações diferem ou há sobreposição. O CSV comparativo inclui o Brasil e as diferenças de cada área para ele, em A e em B.

## Três exportações

- Áreas e diferenças: uma linha por mês/área selecionada; três valores locais, três brasileiros e três diferenças, nível/código/nome e procedência de ambos.
- Ranking: mesmas informações para um mês, na ordem e com posição entre as áreas selecionadas.
- Comparação A/B: quatro indicadores por área, valores/diferenças entre períodos, Brasil A/B e diferenças Área − Brasil em cada período; método e janelas identificados.

CSV UTF-8 com BOM, ponto e vírgula, CRLF e vírgula decimal. Textos de área e indicador são canônicos. Valores, origem, IDs e datas são validados antes de exportar; números negativos permanecem numéricos. Dados incompletos impedem a exportação do recorte, sem substituir ausências por zero.

Downloads usam bytes preparados a partir do retrato da tela, sem nova leitura no clique. Arquivos CLI são publicados completos por hard link sem sobrescrever destino existente; disco local com suporte a hard links é necessário nessa rota. Tabelas largas podem ser roladas horizontalmente no celular.

## Fonte, lotes e amostra

Fonte: [IBGE / SIDRA, tabela 7060](https://sidra.ibge.gov.br/tabela/7060), classificação 315, categoria 7169 (Índice geral), variáveis 63, 69 e 2265. Mesma tabela, medidas e meses para as áreas e o Brasil. Os grupos regionais não fazem parte desta entrega.

As consultas usam uma origem HTTPS fixa, sem token, com os limites/timeouts existentes. Cada requisição de observações contém no máximo 24 meses. A amostra exige quatro requisições: 2020–2021, 2022–2023, 2024–2025 e janeiro–outubro/2026. Atualização incremental revisita 24 meses e procura novos períodos; --full reconfere desde 2020.

Todas as respostas precisam validar 17 localidades exatas, níveis e códigos, nomes esperados, três medidas, unidade e meses contínuos. São aceitas somente duas grafias conhecidas da fonte para UF: Nome - UF e Nome (UF). Resposta inesperada não renomeia silenciosamente uma área.

sample/areas/ibge-7060.json é um pacote radar-areas-v1: guarda os corpos JSON originais de cada resposta como texto, URL e SHA-256 individual. O manifesto registra o SHA-256 do pacote, metadados, data de obtenção e URLs/hashes das partes. Cada hash individual pode ser conferido sobre body.encode("utf-8"). O pacote é arquivado por hash no diretório raw do banco, preservando seus corpos para inspeção.

O limite de 2 MiB vale por resposta e para o pacote total; o coletor também interrompe quando a soma dos corpos excede o limite. A amostra está bem abaixo dele. Um crescimento além desses limites exige adaptar a estratégia em outra versão; não se remove a proteção silenciosamente. Falha em uma parte impede publicar todo o lote regional.

## Banco, qualidade e histórico

Migração transacional 3→4 cria dimensão de áreas, observações, tentativas e mudanças regionais. O histórico nacional e dos grupos é preservado. Dados, eventos de mudança e sucesso da tentativa regional são confirmados numa mesma transação, sob o bloqueio local. Uma interrupção antes do commit desfaz ambos e a tentativa vira INTERRUPTED na próxima abertura.

A primeira importação regional cria 4182 inclusões por campo (1394 × 3). Reconferir números iguais não cria alterações, mesmo mudando a coleta que os conferiu. O histórico usa área com nível/código e permite filtro por área, inclusive Brasil. O CSV do histórico passa a incluir as colunas Area ID e Area; consumidores que dependam de posições fixas devem conferir o cabeçalho.

A central mostra um terceiro conjunto, Áreas do IPCA, com quatro verificações. O CSV da qualidade passa a ter doze linhas nos três conjuntos. Antes de abrir a seção regional ou importar seus dados, o conjunto regional pode aparecer Sem dados. Filtros da central não disparam consulta online.

Os três conjuntos têm publicações independentes. A falha regional preserva sua base anterior e não apaga uma atualização nacional ou dos grupos já concluída. Os novos dados regionais mantêm sua referência do Brasil na mesma transação; não misturam essa referência com a tabela 1737 em outra data.

## CLI

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao demo --dataset areas
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset areas
.\.venv\Scripts\python.exe -m radar_inflacao update --dataset areas --full
.\.venv\Scripts\python.exe -m radar_inflacao export --dataset areas --areas N7:3501 N6:5300108 --from 2024-01 --to 2024-03 --output exports\areas.csv
.\.venv\Scripts\python.exe -m radar_inflacao quality-export --report changes --dataset areas --area N7:3501 --kind ADDED --output exports\historico-sp.csv
~~~

Omitir --areas exporta as 16; a referência brasileira acompanha cada linha. --data-dir continua disponível antes do comando. demo/update sem --dataset incluem os três conjuntos; atualizar.cmd faz a atualização conjunta, sob demanda.

## Atualizar outra instalação

Encerre o aplicativo e preserve data/ antes de substituir o código. Inicie a nova versão normalmente; o banco migra para 4. Versões até 0.4.1 não abrem esquema 4. Guarde uma cópia anterior compatível se precisar reverter. Não compartilhe o DuckDB por pasta de rede/sincronizada com múltiplos escritores.

[Validação desta entrega](VALIDACAO-0.5.0.md) · [Central de qualidade](QUALIDADE.md) · [Arquitetura](ARQUITETURA.md).
