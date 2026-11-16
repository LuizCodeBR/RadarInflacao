# Validação — Radar da Inflação 0.1.0

15/11/2026, horário de São Paulo (coletas e parte dos registros em UTC já em 16/11). Implementação inicial no D:. Nenhum serviço pago, chave de API, conta de nuvem ou agendamento criado.

## Ambiente e execução

Windows; Python principal 3.13.14 em D:/Ferramentas/Python/uv-managed, ambiente do projeto em .venv. Python 3.12.13 instalado no mesmo diretório de ferramentas exclusivamente para conferir compatibilidade. DuckDB 2.0.0, Streamlit 1.67.0 e dependências fixadas em uv.lock/requirements.

- Python 3.13.14: **52 testes aprovados**, zero falhas, em 5,87 segundos; Ruff aprovado.
- Python 3.12.13: **52 testes aprovados**, zero falhas, em 9,53 segundos.
- Instalação limpa: cópia sem .venv, banco ou cache; preparar.cmd -Python com o executável gerenciado e -UsarPip criou venv e instalou os requisitos convencionais. testar.cmd -UsarPip: **52 aprovados**, em 7,91 segundos.
- Sintaxe dos iniciadores Bash conferida com bash -n. Execução nativa Linux/macOS ainda não realizada.
- Workflow GitHub Actions preparado para Windows/Linux × Python 3.12/3.13. Repositório Git local; nenhuma execução remota ou publicação foi realizada nesta etapa.
- Iniciadores Windows executados com Windows PowerShell, sem alteração permanente de política ou PATH.

## Cobertura dos casos

Contrato do IBGE, valores zero/negativos, ausência/NaN/formato inválido, mudança de unidade/localidade/classificação, chaves duplicadas, continuidade dos meses, metadados alterados e validação ativa com Python -O.

Importação repetida sem duplicação; revisão de valor; janela de 24 meses; reconferência integral; procedência por mês e proteção contra substituir dados online pela amostra. Falha de rede registrada, rollback de gravação parcial, arquivo bruto alterado recusado, lock real contra outro processo, tentativa interrompida sinalizada e esquema desconhecido recusado.

Cliente HTTP com retentativas limitadas, timeout simulado, 4xx/redirecionamento recusados e corpo grande. CLI, exportação sem sobrescrita, três medidas e precisão decimal no CSV. Interface AppTest com filtros, acumulados corretos, intervalo invertido, falha da fonte, base anterior preservada e histórico da falha exibido.

As contagens não são percentual de cobertura nem auditoria externa.

## Fonte real

Amostra oficial obtida em **16/11/2026 às 00:31:35 UTC** (15/11 às 21:31:35 em São Paulo), de janeiro/2020 a outubro/2026, 82 meses. Arquivo de dados com 4586 bytes.

SHA-256 da resposta completa:
14b5fcd7967f8c00314697143e98208a9f54863494b84f0e390286d667927776

SHA-256 dos metadados:
ba89a9fa28dafb020ed28afda19a56f543bdedd1d5a893ff6c0d62b96483d2f2

- Coleta real completa em base separada: 82 inseridos, zero corrigidos, mesmo hash da amostra.
- Segunda coleta real incremental: 24 meses, 2024-11 a 2026-10, zero novos/corrigidos, 24 sem alteração e total preservado.
- A interface também atualizou pela API real e sinalizou BASE MISTA para os meses mantidos da amostra.
- O conjunto de meses é o disponível na obtenção; o aplicativo consulta metadados para descobrir novos períodos em atualizações futuras.

## Navegador e imagens

Servidor real iniciado pelo iniciar.cmd em porta 8502 e pasta de dados separada. Chromium de testes já disponível no D: foi reutilizado; Node/Playwright não são dependências para executar o projeto.

Verificados:
- Abertura e aviso AMOSTRA INCLUÍDA.
- Filtro janeiro–março/2024: mensal 0,16%, no ano 1,42%, em 12 meses 3,93%, iguais à fonte.
- Download real do CSV com BOM, separador e valores do período.
- Atualização manual pelo IBGE e identificação da procedência mista.
- Layout mobile com 412 px de largura sem exceder a tela.
- Capturas desktop e mobile inspecionadas. Resoluções de captura maiores em altura permitem mostrar indicadores/gráfico; o teste de largura utilizou viewport mobile 412 × 915.

Primeira tentativa de automação encontrou a lista virtualizada de meses; o seletor passou a pesquisar o mês antes de selecionar. Uma rodada rápida entre mudanças de filtro exigiu aguardar o período aplicado; a tela agora o identifica explicitamente. A execução final foi aprovada.

Um aviso asyncio/Windows de conexão encerrada apareceu ao fechar um navegador em uma rodada inicial; o fluxo final não apresentou esse aviso nem falha de dados. Não houve modificação de bibliotecas instaladas para ocultá-lo.

## Evidências e entrega

Evidências locais ignoradas pelo Git:
.cache/testes-final.log, .cache/testes-312.log, .cache/instalacao-limpa.log, .cache/testes-instalacao-limpa.log, .cache/coleta-real.log, .cache/coleta-incremental-real.log e .cache/navegador-pronto.log.

ZIP fonte em D:/Projetos/Entregas/RadarInflacao-0.1.0, com checksum e instruções. Não inclui .venv, .cache, data, credenciais ou instalações de Python. Conferidos links da documentação e integridade da amostra; encerrados os servidores de ensaio antes de concluir.

## Limites

Validação local Windows, testes de interface simulados e navegador real desktop/mobile emulado. Sem teste em aparelho físico ou execução Linux/macOS nativa. Não há promessa de alto volume, operação multiusuário pública, revisão histórica imutável ou atualização automática. Nenhum link online foi publicado nesta primeira etapa.
