# Central de qualidade e atualização — 0.5.0

## Usar no painel

1. Execute iniciar.cmd; abra http://localhost:8501.
2. Em Análise, escolha Qualidade e atualização.
3. Consulte os três conjuntos: índice geral, nove grupos e áreas do IPCA. Cada um mostra registros, período, origem, última tentativa, última publicação e quatro verificações.
4. Use filtros do histórico por conjunto, tipo de evento, mês e grupo. Deixe meses vazios para não restringir. O grupo fica disponível ao escolher Nove grupos.
5. Baixe CSV da qualidade ou CSV das mudanças filtradas.

A central é um painel web local responsivo. As tabelas podem ser roladas horizontalmente no celular. Não há instalação de aplicativo nativo ou hospedagem nesta etapa.

## Verificações e interpretação

| Verificação | Regra |
| --- | --- |
| Cobertura | Todos os meses desde janeiro/2020 até o último local; nove grupos por mês e vínculos válidos |
| Valores | Taxas decimais finitas; três medidas nacionais, quatro dos grupos; pesos e ausência histórica conforme contrato |
| Procedência | Modo, data com fuso, SHA-256, UUID e vínculos com publicações concluídas; vínculos do histórico |
| Disponibilidade | Comparação com o último mês declarado nos metadados registrados, com identificação da data e modo |

A ausência conhecida de 12 meses dos nove grupos de janeiro–novembro/2020 é informação aceita, nunca zero. Demais ausências são erro. A conferência de soma de pesos exige os nove grupos e tolerância de 0,05 p.p.

Situação OK significa que as verificações locais aplicáveis passaram. Isso não confirma a exatidão econômica de cada valor, a autenticidade de um disco adulterado ou disponibilidade em tempo real. Resultado de disponibilidade da amostra é informativo, não consulta online.

Última tentativa e última publicação são distintas. Uma coleta recusada mantém a última base válida e aparece com falha/etapa. Se metadados válidos declararem mês mais recente e o download falhar, o alerta de período pendente aparece mesmo sem publicação nova. Falha antes de validar metadados não confirma um novo período.

Há 20 tentativas recentes por conjunto na tabela; última publicação e referência são consultadas separadamente, sem depender de estar entre essas 20. Horários vêm com fuso UTC (+00:00).

## Histórico por campo

Cada inclusão é um evento por indicador. Exemplo: um mês nacional novo gera três inclusões; um mês dos grupos gera 36. Nas duas amostras nacionais há 3198 inclusões: 82 × 3 + 738 × 4. A regional acrescenta 4182 (1394 × 3), totalizando 7380 numa importação dos três conjuntos. Os 99 campos históricos vazios também são inclusões explícitas, sem valor numérico novo.

Alterações detectadas guardam mês, grupo, indicador, antes/depois, coleta anterior/atual, horário e hash da resposta atual. Uma nova conferência de valores iguais não cria alterações, mesmo que mude sua procedência. Não se atribui automaticamente uma revisão oficial a uma divergência observada entre coletas.

O índice analítico continua mostrando o último valor publicado. O histórico é acrescentado junto com os dados, na mesma transação. Falha de gravação desfaz ambos. Após encerramento forçado, a tentativa remanescente recebe INTERRUPTED na próxima abertura, com a etapa preservada.

O histórico começa na migração para esquema 3. A tela informa quantos registros já existiam. Não há reconstrução das diferenças antigas a partir de suposições ou reconversão de arquivos brutos. O banco não é um registro inviolável contra usuários com escrita no disco.

## Demonstração offline

Ative Usar demonstração offline separada. A aplicação cria .cache/quality-demo com um marcador próprio e estes passos:

1. Importação das duas amostras reais identificadas como amostra.
2. Alteração sintética do último valor mensal do índice geral e de Alimentação e bebidas para 9,99.
3. Reconferência idêntica, com zero alterações adicionais.
4. Tentativa de lote de grupos com mês faltante: recusada antes de publicar.

O histórico padrão mostra duas alterações, ambas Simulação offline. O resumo dos grupos mostra tentativa falha, mantendo publicação anterior válida. A central principal e o exemplo usam bancos separados. A atualização da base principal fica desabilitada enquanto a demonstração está ativa; desative para voltar.

A preparação repetida reutiliza o cenário sem acrescentar novas tentativas. Pasta pré-existente sem marcador é recusada. Marcador sozinho não certifica uma demonstração pronta: é necessário banco existente com execuções simuladas concluídas. Links, junções e arquivos compartilhados por hard link nos caminhos verificados são recusados. Em caso de preparação interrompida, a pasta é preservada e a interface informa o problema; não apaga ou reinicia automaticamente conteúdo encontrado. A pasta não entra no ZIP. Primeiro uso do projeto prepara dependências com internet; o exemplo não precisa de rede depois disso.

## CSV e filtros

CSV UTF-8 com BOM, ponto e vírgula, linhas CRLF e vírgula decimal, sem arredondar os valores guardados. Ausência válida fica vazia. Valor anterior vazio em Inclusão significa que ainda não existia aquele registro, distinguível do indicador histórico indisponível pelo tipo do evento e seu campo.

Relatório de qualidade: uma linha por verificação (doze nos três conjuntos), situação, período/quantidade, última tentativa/publicação, início do histórico, modos, etapa/detalhe da falha e referência dos metadados. Refere-se às bases completas; filtros do histórico não restringem as verificações.

Relatório de mudanças: uma linha por evento, com filtros aplicados. A tabela exibe páginas de 50, mas o CSV contém todos os eventos filtrados até o limite de 10000, não apenas a página. Se exceder, a exportação é recusada e pede refinamento. O total encontrado é explícito. O histórico armazenado não é removido automaticamente.

Textos/tipos/procedência são validados antes da exportação. O total precisa corresponder aos eventos disponíveis; identidades duplicadas e eventos fora dos filtros são recusados. O vínculo anterior de uma alteração precisa existir, ser de coleta concluída e diferente da coleta atual. Eventos com vínculo ausente não desaparecem da consulta: ficam detectáveis e bloqueiam a exportação correspondente. Campos hostis são recusados; números negativos válidos permanecem numéricos. Arquivo preparado usa o mesmo snapshot das tabelas; clicar em baixar não consulta novamente o banco. Atualizar a página ou mudar filtro produz nova consulta. Após digitar um mês, pressione Enter e aguarde a legenda Histórico aplicado refletir o período desejado antes de baixar. Uma edição ainda não aplicada não altera os bytes já preparados.

Na CLI, o arquivo completo é publicado sem substituir destino existente. Requer disco local com suporte a hard links (validado no D:/NTFS); download no navegador não tem esse requisito. Confira limites de interrupção e sistema de arquivos na [revisão da exportação](REVISAO-0.2.1.md).

## Comandos

~~~powershell
.\.venv\Scripts\python.exe -m radar_inflacao quality
.\.venv\Scripts\python.exe -m radar_inflacao quality-export --output exports\qualidade.csv
.\.venv\Scripts\python.exe -m radar_inflacao quality-export --report changes --kind CHANGED --output exports\mudancas.csv
.\.venv\Scripts\python.exe -m radar_inflacao quality-export --report changes --kind ADDED --dataset groups --group 7170 --from 2024-01 --to 2024-03 --output exports\inclusoes.csv
.\.venv\Scripts\python.exe -m radar_inflacao quality-demo
.\.venv\Scripts\python.exe -m radar_inflacao --data-dir .cache\quality-demo quality
~~~

quality não importa amostras nem consulta a rede. Em base vazia informa Sem dados. O painel mantém a preparação inicial das amostras quando necessário. quality-demo usa somente a pasta fixa do projeto e recusa --data-dir. Respeita-se RADAR_DATA_DIR nos comandos de consulta/exportação normais; ele não redireciona a criação do exemplo. A pasta reservada da demonstração e suas subpastas são recusadas como base principal do painel e nos comandos demo/update. Consulta/exportação explícita dessa pasta continua permitida.

## Armazenamento e compatibilidade

Arquivos desta instalação em D:/Projetos/RadarInflacao. A versão 0.5.0 usa esquema 4, com migração transacional de 3→4 e encadeada de 1→2→3→4. Não há dependência nova, conta, recurso pago, serviço de banco ou tarefa agendada. Iniciadores Windows/Linux permanecem; Windows validado, execução nativa Linux/macOS e celular físico não foram feitos nesta etapa.

Antes de atualizar outra instalação, encerre o aplicativo e preserve data/. Versões até 0.4.1 recusam esquema 4. Não use a base em pasta de rede/sincronizada com múltiplos escritores. Bloqueios e transações só coordenam programas que respeitam o protocolo do projeto.

[Revisão 0.4.1](REVISAO-0.4.1.md) · [Validação inicial](VALIDACAO-0.4.0.md) · [Arquitetura](ARQUITETURA.md).

## Áreas na versão 0.5.0

O terceiro conjunto Áreas do IPCA inclui as 16 áreas e Brasil da tabela 7060. Tem quatro verificações, histórico por campo e filtro de área, inclusive Brasil. O resumo CSV contém doze verificações nos três conjuntos. O CSV de mudanças acrescenta Area ID e Area; Grupo ID continua específico dos grupos. O limite de 10000 eventos continua por recorte. A demonstração offline da central mantém seus dois cenários sintéticos; o conjunto regional nela fica Sem dados. Para explorar dados regionais oficiais, use Comparar áreas na base principal. [Guia regional](AREAS.md).
