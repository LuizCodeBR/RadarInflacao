# Validação — Radar da Inflação 0.4.0

16/11/2026, horário de São Paulo. Implementação em D:/Projetos/RadarInflacao. Central de qualidade, histórico de mudanças, CSV, demonstração offline e migração para esquema 3. Sem serviços pagos, nuvem, conta ou agendamento.

## Testes automatizados

- Windows / Python 3.13.14, testar.cmd: **268 aprovados**, 211,66 s; Ruff aprovado.
- Windows / Python 3.12.13: **268 aprovados**, 212,72 s.
- 39 casos novos em tests/test_quality.py, além dos 229 anteriores. Os testes de processos da revisão dos grupos foram ampliados para verificar também histórico, relatório preparado e etapa após commit/interrupção.
- As duas suítes foram executadas simultaneamente em bases/temporários separados; tempos são observações destas execuções, sem comparação de velocidade entre versões.

Os cenários cobrem:

1. Primeira importação: 82 registros nacionais, 738 dos grupos, 3198 eventos de inclusão por campo e 99 ausências históricas explícitas.
2. Reimportação/reconferência sem eventos falsos; alteração de um campo com valores/IDs/hash exatos; mês novo como inclusão.
3. Falha no histórico ou na publicação: rollback de mudanças e valores juntos; tentativa falha e última publicação preservada.
4. Metadados válidos com mês novo e falha de download: disponibilidade pendente com base anterior preservada. Metadados inválidos não confirmam novo período.
5. Base vazia, cobertura com lacunas, peso inválido, ausência inesperada e procedência adulterada: resultados explicados, sem crash da central.
6. Filtros válidos/inválidos, CSV numérico negativo e campos vazios válidos, contextos decimais restritivos, campos hostis e recusa de relatório truncado.
7. CSV CLI sem sobrescrita; filtro inválido não cria arquivo.
8. Migração 2→3 preservando linhas, sem diferenças retroativas; falha durante a migração desfaz estruturas novas. Migração 1→3 continua coberta pelo teste existente.
9. Cenário offline separado, identificável, repetível e com recusa de pasta não identificada.
10. Interface via AppTest: central, simulação, filtro de grupo, erro de mês, dois downloads sem rerun.

A contagem não é percentual de cobertura nem certificação de segurança. Testes comuns não dependem de IBGE online.

## Concorrência e recuperação

O teste existente executa o pipeline real de grupos em outro processo, suspenso durante uma transação. Nova leitura da central e outro escritor recebem BusyError; CSV preparado continua idêntico. Ao concluir, a alteração e o evento são publicados juntos. Ao matar o processo, ambos são desfeitos, a etapa PUBLISH permanece e a tentativa recebe INTERRUPTED na reabertura. Nova coleta posterior conclui, sem duplicações.

Os testes anteriores de disputa pelo mesmo arquivo CSV, precisão, proteção de textos e snapshots continuam aprovados. O protocolo exige disco local e acesso coordenado; um programa externo que ignore o lock não está coberto. O histórico não é inviolável contra edição do disco.

## Migração da instalação principal

Antes da migração foi criada uma cópia de radar.duckdb, e WAL se existente, em .cache/antes-migracao040, sob o bloqueio local. Dados e tentativas das quatro tabelas anteriores foram serializados no banco e comparados antes/depois.

Resultado: esquema 2→3, **82 observações nacionais e 738 de grupos preservadas**, tentativas anteriores preservadas, zero mudanças retroativas inventadas. O histórico prospectivo começa na migração. Metadados de disponibilidade anteriores à central não são reconstruídos automaticamente; a primeira nova atualização sob demanda registra a referência.

A cópia anterior é uma proteção desta migração, não uma rotina automática de backup. Para preservar toda a instalação em outra máquina, guarde data/ com o aplicativo encerrado.

## Navegador real

Chromium já instalado no D:, servidor temporário 127.0.0.1:8506 e base de ensaio .cache/browser040, separados da instalação principal.

- Central com quatro verificações por conjunto, último sucesso separado da última tentativa, dois relatórios e paginação.
- CSV de inclusões com 3198 eventos e BOM; CSV da qualidade com oito verificações.
- Outro processo publica alteração sintética em transação: downloads preparados de qualidade e mudanças permanecem byte a byte iguais durante o lock; nova página recebe a mensagem de base ocupada.
- Após commit, nova sessão encontra a mudança e seu valor; sessão anterior mantém o arquivo já preparado.
- Demonstração local explícita com duas mudanças, etapa da falha de grupos e CSV marcado Simulação offline. Atualização da base principal desabilitada enquanto o exemplo está ativo.
- Filtros por conjunto e mês inválido; desktop 1440 pixels e mobile emulado 412 pixels, sem transbordamento da página; botões de download acessíveis.
- Capturas conferidas visualmente em docs/imagens/qualidade-*.png.

Uma primeira execução do roteiro encontrou detach do controle durante a seleção automatizada. O roteiro passou usando a busca do seletor e aguardando sua atualização; não foi necessária alteração de produto para esse caso. Os ensaios de concorrência já haviam concluído antes dessa etapa visual.

Não houve execução em celular físico ou de fórmulas em Excel/LibreOffice. A proteção CSV é verificada na serialização. Eventuais transformações posteriores por outros programas estão fora desse teste.

## Distribuição

Mesmas dependências: 45 pacotes resolvidos no lock, com versão local do projeto atualizada para 0.4.0. Python 3.12/3.13; sem extensão nova, Docker ou servidor de banco.

Preparação limpa em .cache/validacao040/RadarInflacao aprovada com preparar.cmd, usando uv já disponível e Python 3.13 no D:. Importação 82+738, reimportação sem duplicações, relatório de oito verificações, CSVs filtrados e simulação concluíram. O painel da central com demonstração e dois downloads passou via AppTest na cópia limpa. A rota pip permanece disponível, mas não foi repetida nesta etapa. O ZIP fonte exclui ambiente, caches, banco principal, simulação preparada e arquivos de exportação. Conferências de preparação limpa, importação e pacote extraído são registradas nos logs locais da entrega.

Workflow Windows/Linux ampliado com consulta e exportações da central; não foi executado remotamente. Windows executado; Linux/macOS nativos não foram testados nesta etapa. Nenhum repositório remoto foi configurado ou publicação realizada.

## Evidências locais

- .cache/testes040-final.log e .cache/testes312-040.log.
- .cache/testes040-quality2.log: 82 casos direcionados aprovados.
- .cache/migracao040.log e .cache/antes-migracao040/.
- .cache/navegador040.log: concorrência e downloads concluídos.
- .cache/navegador040-final.log: central/filtros/mobile concluídos.
- .cache/instalacao040.log, .cache/instalacao040-smoke.log e .cache/pacote040.log.

Esses arquivos de ensaio ficam no D: e são ignorados pelo Git; o guia e esta validação acompanham o pacote fonte.
