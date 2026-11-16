# Arquitetura — Radar da Inflação 0.1.0

## Escopo e escolhas

Uma aplicação Python com módulos por responsabilidade. Interface, CLI e testes chamam o mesmo pipeline. O produto inicial cobre três medidas oficiais do IPCA nacional desde 2020, uma fonte e atualização manual.

| Módulo | Responsabilidade |
| --- | --- |
| model.py | Meses, números decimais, JSON sem chaves duplicadas e contrato do IBGE |
| source.py | Origem HTTPS fixa, timeouts, limite de tamanho e retentativas limitadas |
| pipeline.py | Amostra/coleta, validação integral, arquivo bruto e publicação transacional |
| storage.py | DuckDB, esquema 1, lock entre processos e consultas parametrizadas |
| report.py | CSV com valores e procedência por mês |
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
