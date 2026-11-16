# Arquitetura — Radar da Inflação 0.2.1

## Escopo e escolhas

Uma aplicação Python com módulos por responsabilidade. Interface, CLI e testes chamam o mesmo pipeline. O produto cobre três medidas oficiais do IPCA nacional desde 2020, comparações locais, uma fonte e atualização manual.

| Módulo | Responsabilidade |
| --- | --- |
| model.py | Meses, números decimais, JSON sem chaves duplicadas e contrato do IBGE |
| source.py | Origem HTTPS fixa, timeouts, limite de tamanho e retentativas limitadas |
| pipeline.py | Amostra/coleta, validação integral, arquivo bruto e publicação transacional |
| storage.py | DuckDB, esquema 1, lock entre processos e consultas parametrizadas |
| analysis.py | Resumo de intervalos, composição decimal, comparação e apresentação de taxas |
| report.py | CSV mensal com procedência e CSV de comparação com método e janelas |
| cli.py | Comandos e identificação da pasta independente |
| app.py | Leitura, filtros, indicadores, gráfico, download e botão de atualização |

## Fluxo

1. Adquirir o lock local antes de abrir o banco. Outra operação recebe mensagem clara.
2. Registrar tentativa RUNNING.
3. Ler amostra e conferir hashes, ou consultar metadados e dados da API.
4. Validar todo o lote: Brasil/N1/1, variáveis, unidade %, meses e valores finitos.
5. Arquivar resposta e metadados validados por SHA-256.
6. Em uma transação, inserir/corrigir meses, associar a procedência e concluir SUCCESS.
7. Falha de publicação desfaz a transação; a tentativa recebe FAILED e a base anterior continua.
8. Na próxima abertura, tentativas RUNNING remanescentes recebem INTERRUPTED.

## Persistência e concorrência

observation tem uma linha por mês, três DECIMAL(14,6) e vínculo à última coleta que conferiu o mês. ingestion guarda modo, origem, período, hashes, situação e contagens de novos/corrigidos/sem alteração. schema_version=1 recusa versão desconhecida.

FileLock usa bloqueio entre processos; a aplicação mantém o lock durante a operação e fecha a conexão depois. Isso também coordena consultas da interface/CLI e atualizações. Custo: durante coleta, uma consulta concorrente pode ser recusada para nova tentativa. Esta arquitetura é local, em um computador e disco convencional; não declara suporte a pasta sincronizada, compartilhamento de rede ou múltiplos servidores.

Duas execuções de uma coleta válida mantêm o mesmo número de meses, mas geram tentativas distintas no histórico. Valores sem alteração também recebem a procedência da conferência mais recente. A contagem unchanged refere-se aos números; não significa ausência de registro operacional.

## Atualização incremental

Sem base: buscar janeiro/2020 até o último mês declarado nos metadados. Com base: revisitar os 24 meses a partir do mês mais recente existente e buscar os posteriores. --full reconcilia desde 2020. Revisões mais antigas que a janela exigem essa opção. Valores novos substituem o estado analítico atual; não há tabela de todas as versões de cada valor.

Meses, medidas ou unidade divergentes recusam o lote completo. Ausência não vira zero. O total da série não é identificado como online se só uma parte foi consultada: o modo é preservado por mês.

## Rede e falhas

Somente a origem fixa do IBGE é utilizada, sem credenciais. HTTPS verificado; redirecionamentos não são seguidos. Máximo 2 MiB por resposta, três tentativas para falhas de transporte/429/5xx, espera limitada entre tentativas e timeout de conexão/leitura. Não há garantia absoluta de duração total em qualquer comportamento de rede.

Resposta inválida não é publicada. Arquivos brutos validados podem permanecer se a gravação posterior falhar; só as observações de transações concluídas são exibidas. Dados locais não são enviados para terceiros.

## Valores e leitura

Decimal evita usar ponto flutuante no armazenamento e na conferência de igualdade. Gráfico/tabela usam conversão para apresentação; indicadores exibem duas casas. O CSV preserva a precisão decimal armazenada. Os acumulados vêm da fonte oficial, sem somar percentuais. Cada consulta de tela carrega os dados e o histórico no mesmo acesso coordenado.

Datas de execução no banco são UTC. Momento original da amostra permanece no manifesto e na procedência, separado da data da importação local.

## Distribuição

Python 3.12/3.13, dependências fixadas por uv.lock e requirements exportados. Iniciadores usam venv e pip, ou uv existente. Cache e temporários ficam na pasta do projeto; o pacote fonte não inclui banco, ambiente ou caches.

O painel escuta em 127.0.0.1. Nenhum login, cobrança, hospedagem, API com token ou agendamento é necessário. Streamlit organiza a interface; DuckDB evita um servidor de banco separado. O custo é não oferecer, nesta arquitetura, operação pública concorrente de múltiplos usuários.

## Análise e comparações na versão 0.2.0

analysis.py recebe o mesmo snapshot já carregado pela tela. Suas funções são independentes de Streamlit, banco e rede, não alteram as linhas de entrada e não persistem resultados derivados. Uma coleta concorrente posterior não mistura versões dentro da comparação já calculada.

PeriodSummary contém as datas, quantidade de meses, composição das taxas mensais e as três medidas oficiais do último mês. PeriodComparison combina dois resumos, calcula A − B em pontos percentuais e identifica sobreposição e durações diferentes.

Cada intervalo precisa ter todos os meses, sem duplicações. O modo automático gera a janela exata e não a trunca para caber na base. Intervalos insuficientes produzem uma mensagem; gráfico e CSV mensal de A continuam disponíveis.

Os cálculos usam Decimal com contexto local de precisão proporcional ao intervalo, sem herdar uma precisão insuficiente do chamador. As diferenças usam os valores anteriores ao arredondamento. A tela aplica ROUND_HALF_UP em duas casas e evita exibir zero negativo; a exportação preserva a precisão calculada. Não há anualização nem divisão por uma taxa possivelmente zero.

A composição é identificada como estimativa, porque as taxas mensais publicadas já têm arredondamento. Os acumulados oficiais da fonte são preservados e nunca substituídos por essa composição. Não houve alteração no esquema 1, nos dados da amostra ou nas dependências.


## Revisão 0.2.1: fronteiras de exportação

Cálculos usam um Context explícito, isolando também limites de expoentes e traps externos. Taxas recebidas pela análise/exportação precisam respeitar a representação da fonte, inclusive até seis casas decimais. A serialização usa format(f), sem normalize(), para preservar precisão.

CSV mensal valida mês, modo, data com fuso, hash e UUID. Campos descritivos de comparação rejeitam prefixos de fórmula e controles. Valores negativos válidos permanecem numéricos. Uma exportação mensal inválida é tratada na interface sem encerrar a consulta.

Na CLI, csv_bytes() termina antes de criar o temporário; publish_csv() grava no diretório final, sincroniza bytes e cria o destino por os.link(), que recusa um destino existente. finally remove o temporário. Isso depende de hard links no volume e não promete recuperação de falhas físicas ou limpeza após encerramento abrupto.

Os downloads usam bytes preparados com o snapshot exibido e on_click="ignore", sem nova leitura só por baixar. As comparações continuam locais a cada execução e não compartilham cache mutável entre sessões. Atualizar a página ou alterar um filtro produz uma nova consulta.

Veja [achados e evidências](REVISAO-0.2.1.md).
