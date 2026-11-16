# Radar da Inflação

Pipeline de dados públicos do **IPCA nacional**, com Python, SQL/DuckDB e painel Streamlit. Coleta dados do IBGE, valida o contrato da fonte, preserva a última base válida e registra origem, hash e resultado de cada execução.

**Versão inicial 0.1.0 · execução local · sem conta, chave de API ou recurso pago.**

![Painel do Radar da Inflação](docs/imagens/painel-desktop.png)

## Experimentar no Windows

Pré-requisito: **Python 3.12 ou 3.13**. Extraia o projeto em pasta gravável, por exemplo D:\Projetos\RadarInflacao. Abra iniciar.cmd ou, no terminal da pasta:

~~~powershell
.\iniciar.cmd
~~~

Abra **http://localhost:8501**. A primeira execução instala dependências fixadas em .venv; precisa de internet. Depois, a amostra incluída permite consultar o painel sem acessar o IBGE. Mantenha o terminal aberto; Ctrl+C encerra.

Para outra porta:

~~~powershell
.\iniciar.cmd -Port 8502
~~~

Se o Python não estiver no PATH, informe seu executável:

~~~powershell
.\preparar.cmd -Python 'D:\Ferramentas\Python\python.exe'
~~~

O caminho acima é um exemplo; use o local da sua instalação. Não exige Node, Docker, PostgreSQL, extensão do VS Code ou hospedagem. Neste computador, o Python foi preparado no D: pelo uv já existente.

## Linux/macOS

Com Python 3.12 ou 3.13 e suporte a venv/pip:

~~~bash
bash iniciar.sh
# Se python3 não for a versão desejada:
RADAR_PYTHON=python3.13 bash iniciar.sh
~~~

O iniciador prepara o ambiente e abre o mesmo painel local. A validação realizada nesta entrega foi no Windows; o workflow preparado inclui Windows/Linux.

## O que funciona

- Amostra real do IBGE: janeiro/2020 a outubro/2026, 82 meses e três medidas por mês.
- Filtros de início/fim, indicadores oficiais, gráfico e tabela com procedência.
- CSV UTF-8 com BOM, ponto e vírgula e vírgula decimal.
- Atualização sob demanda pela API do IBGE.
- Reconsulta dos últimos 24 meses existentes e busca de meses novos, sem duplicação.
- Reconferência integral desde 2020 para revisões mais antigas.
- Histórico de execuções, arquivos brutos identificados por SHA-256 e gravação transacional.
- Validação de Brasil, tabela, periodicidade, unidade %, três medidas e meses contínuos.
- Falha de rede, JSON inválido ou valor ausente preservam a base válida anterior.
- Bloqueio entre processos para coordenar o arquivo DuckDB.

O painel distingue **amostra incluída**, **base consultada** e **base mista**. Atualizar só uma parte não passa a apresentar toda a série como recém-coletada.

## Atualizar e testar

~~~powershell
.\atualizar.cmd
.\atualizar.cmd -Completo
.\testar.cmd
~~~

No Linux/macOS:

~~~bash
bash atualizar.sh
bash atualizar.sh --full
bash testar.sh
~~~

Atualizar exige internet e acontece somente quando solicitado. Os testes comuns usam respostas controladas e a amostra local, sem depender da rede. O painel também oferece o botão Atualizar pelo IBGE.

## Linha de comando

Depois de preparar o ambiente, no Windows:

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao status
.\.venv\Scripts\python.exe -m radar_inflacao demo
.\.venv\Scripts\python.exe -m radar_inflacao export --from 2024-01 --to 2024-03 --output exports\ipca-2024.csv
~~~

Exportação não substitui um arquivo existente. Para usar outra base independente, a opção global vem antes do comando:

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao --data-dir .cache\ensaio update --full
~~~

RADAR_DATA_DIR também seleciona a pasta. A amostra não substitui uma base que já contém dados consultados online.

## Fonte e significado dos números

IBGE/SIDRA, **tabela 1737**, Brasil: variável 63 (mensal), 69 (acumulado no ano) e 2265 (12 meses). [Documentação da API](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3) · [Tabela](https://sidra.ibge.gov.br/tabela/1737).

Os acumulados são os divulgados pelo IBGE; não são calculados somando taxas mensais. No ano significa desde janeiro, mesmo se o filtro começar depois. O indicador nacional não representa a inflação individual de cada pessoa.

A [amostra](sample/manifest.json) registra URL, momento da obtenção e hashes dos dados/metadados. Os números do período continuam sendo os publicados pela fonte; não se trata de uma previsão ou medição de preços de produtos.

## Arquitetura

~~~mermaid
flowchart LR
    IBGE[API IBGE / tabela 1737] --> COLETA[Cliente HTTP]
    AMOSTRA[Amostra local identificada] --> VALIDACAO[Validação]
    COLETA --> VALIDACAO
    VALIDACAO --> RAW[Arquivos brutos / SHA-256]
    VALIDACAO --> DB[(DuckDB / transação)]
    DB --> PAINEL[Painel Streamlit]
    DB --> CSV[CSV / procedência]
~~~

[Arquitetura e decisões](docs/ARQUITETURA.md) · [Qualidade e testes](docs/VALIDACAO-0.1.0.md) · [Instalação e uso](docs/INSTALACAO.md) · [Dados e limites](docs/DADOS.md).

## Pastas e armazenamento

- src/radar_inflacao/: modelo, fonte, pipeline, persistência, CSV e CLI.
- app.py: interface, sem coleta automática ao consultar filtros.
- sample/: resposta pública do IBGE, metadados e manifesto versionados.
- tests/: regras, rede simulada, banco, concorrência e interface.
- data/: banco, lock e respostas brutas validadas; ignorada pelo Git.
- .venv/ e .cache/: ambiente, downloads, temporários e evidências; ignorados.
- exports/: arquivos gerados; ignorada.

Os iniciadores mantêm ambiente, caches e temporários dentro da pasta do projeto; aqui, no D:. O Python gerenciado foi instalado em D:\Ferramentas\Python\uv-managed. Configurações do editor e do sistema seguem seus próprios locais.

## Limites da primeira versão

Série nacional desde 2020, fonte única e arquivo local. Atualizações e leituras da aplicação usam o mesmo bloqueio; outra operação em andamento pode pedir nova tentativa. Não é um servidor analítico para vários usuários ou gravação distribuída.

O projeto oferece painel web local responsivo; não publica link externo ou aplicativo nativo nesta entrega. Falhas ficam no histórico, e uma interrupção é sinalizada na próxima abertura. Arquivos brutos não substituem um backup da pasta de dados. Não há tarefa agendada ou serviço pago.

**Critério de conclusão da primeira etapa:** amostra + coleta real + validação + persistência + filtros/CSV + testes + execução simples. Novas fontes, regiões e automações ficam para uma decisão separada.
