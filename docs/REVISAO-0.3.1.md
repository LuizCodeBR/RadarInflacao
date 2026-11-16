# Revisão de segurança e concorrência — 0.3.1

16/11/2026, horário de São Paulo. Revisão da versão 0.3.0 em D:/Projetos/RadarInflacao, com nova leitura, reprodução de falhas e testes adversos. Realizada pelo assistente; não é auditoria humana externa ou certificação de segurança.

## Escopo e condições

Nove grupos do IPCA: validação, gráficos, ranking, comparação A/B, CSV, consulta/atualização concorrente e distribuição local. Aplicação limitada a 127.0.0.1, dados públicos, sem conta, credenciais, servidor pago ou tarefa agendada.

A coleta normal já valida a resposta do IBGE antes de publicar. Os testes de objetos CSV falsificados e dados locais corrompidos exercitam limites internos e alterações fora do fluxo normal. Não foi demonstrada entrada remota de fórmula ou alteração do banco pelo navegador. Possuir acesso de escrita ao diretório local continua sendo uma condição de confiança; esta revisão não promete impedir um usuário local de substituir o programa ou todos os dados por outros coerentes.

## Achados reproduzidos e correções

| Achado | Consequência e reprodução | Correção |
| --- | --- | --- |
| Ordenação dependia do contexto decimal | Precisão 3 fazia 1,231 e 1,234 produzirem a mesma chave negativa; o ranking colocava o grupo anterior primeiro. Com Inexact habilitado, ocorria exceção | Decimal.copy_negate(), sem arredondamento ou alteração das flags do chamador; desempate oficial preservado |
| Validação local incompleta antes da análise | Filtros aceitavam taxa NaN, peso negativo, nome alterado e ausência de 12 meses fora da janela histórica; poderiam alcançar apresentação ou cálculos antes da recusa do CSV | Validador comum do retrato local, com tipos, limites, unicidade e pesos; painel recusa dados inconsistentes antes dos gráficos |
| CSV comparativo aceitava objetos incoerentes | Aceitava diferença arbitrária, valor divergente do resumo, zero medidas, medida duplicada, ausência fora da janela ou grupos com períodos diferentes | Conferência de resumos, quatro medidas canônicas, diferenças A − B e mesmas janelas A/B por grupo antes de produzir bytes |
| Gráficos tinham limites diferentes do contrato analítico | 1200 meses × 9 grupos excedem o limite padrão de 5000 linhas do transformador Altair. Composição de taxas extremas pode ser Decimal finito e float infinito | Dados inline já limitados pela aplicação, sem mudar configuração global; detecção de valores não finitos na conversão para gráfico comparativo e aviso explícito, preservando tabela/CSV |

No primeiro conjunto de regressões, **19 casos falharam na versão anterior e 9 já passaram**. Os casos que já passavam confirmaram proteções existentes; não são apresentados como vulnerabilidades novas. O cenário de 10800 registros e as taxas extremas são sintéticos, não projeções nem dados efetivos do IBGE.

## Validação e exportação

- Até 1200 meses e 10800 registros; IDs/nomes canônicos e meses AAAA-MM com dígitos ASCII, desde 2020.
- Pares mês/grupo únicos; intervalos selecionados completos. O painel exige os nove grupos para cada mês da série local.
- Mensal/no ano obrigatórios e taxas decimais finitas dentro do contrato; 12 meses explicitamente None apenas em janeiro–novembro/2020. Campo ausente não equivale a None.
- Pesos entre 0 e 100. Soma dos nove grupos por mês a até 0,05 p.p. de 100; a seleção parcial não tem essa exigência.
- CSV comparativo exige contagens correspondentes às datas, quatro indicadores, métodos/números coerentes com os resumos e diferenças calculadas em contexto isolado. Um resumo não contém todas as observações: a validação não prova a origem de um acumulado inventado de forma internamente coerente.
- Proteções de texto, modo, data com fuso, SHA-256 e UUID permanecem. Taxas negativas são números válidos, sem apóstrofo ou alteração silenciosa.
- Procedência inválida bloqueia os CSVs de dados/ranking. A comparação com números válidos e textos internos continua disponível; seu CSV identifica fonte/método, sem declarar a procedência individual de cada mês.
- Não há HTML externo executado, SQL montado com valores do usuário ou URL livre de coleta. A fonte fixa 7060 herda recusa de redirecionamento, limite de resposta, timeout e retentativas limitadas.

A comparação e seus quatro indicadores compartilham uma única definição. Não houve mudança das fórmulas, janelas ou formato de CSV válido.

## Concorrência em processos reais

O pipeline dos grupos foi suspenso depois de gravar parte de um lote e antes do COMMIT, mantendo o bloqueio da aplicação. Enquanto isso:

1. Nova leitura e outro escritor receberam BusyError.
2. Os dados, ranking e comparação calculados do snapshot anterior mantiveram os mesmos bytes CSV.
3. Ao liberar o escritor, o lote completo passou a SUCCESS; nova consulta recebeu os novos valores, sem duplicação e com os dados nacionais preservados.
4. Ao matar o processo de ensaio antes do COMMIT, a reabertura recuperou os dados anteriores e marcou a tentativa como INTERRUPTED.
5. Uma nova coleta após os dois desfechos concluiu com 216 registros na janela incremental e total de 738 observações.

Duas exportações com conteúdos reais dos grupos disputaram o mesmo destino. Uma publicou; outra recebeu FileExistsError. O arquivo final correspondia a um conteúdo completo, sem mistura ou temporário remanescente em encerramento normal.

A revisão confirmou o protocolo existente; não foi necessário alterar o bloqueio, o esquema ou a transação. As garantias valem para operações que respeitam esse protocolo no mesmo disco local. Escrita externa que ignore o lock e compartilhamentos de rede não estão cobertos. Publicação de CSV pela CLI continua dependendo de hard links; interrupção abrupta pode deixar temporário. Não se declara resistência a falha física/queda de energia.

## Resultados automatizados

- Windows / Python 3.13.14: **229 aprovados**, 89,85 s; Ruff aprovado.
- Windows / Python 3.12.13: **229 aprovados**, 92,47 s.
- 51 casos adicionais: 43 no arquivo de revisão dos grupos e 8 pela aplicação da suíte de rede existente também ao GroupSource.
- Os 178 casos anteriores permanecem; o total não representa percentual de cobertura ou prova de ausência universal de falhas.
- Testes incluem contextos decimais restritivos, objetos comparativos incoerentes, campos hostis, ausência histórica, banco adulterado em base de ensaio, volume máximo de gráfico, limite de float, processos concorrentes e recuperação após encerramento forçado.

Comando reproduzível: testar.cmd; no Linux/macOS, bash testar.sh. A suíte usa amostras e fontes simuladas, sem IBGE online ou credenciais.

## Navegador real

Chromium já disponível no D:, servidor 127.0.0.1:8505, base exclusiva .cache/browser031. Conferidos nove grupos, três gráficos, ranking janeiro/2024, comparação janeiro–março/2024 contra 2023, três CSVs e ausência histórica.

Uma sessão preparou os três downloads. Outro processo manteve uma transação não concluída: os arquivos da sessão inicial permaneceram idênticos byte a byte, e outra página recebeu a mensagem de base ocupada. Após COMMIT, nova sessão recebeu o valor alterado e nova comparação; a sessão anterior continuou oferecendo seus dados originais. A alteração sintética foi revertida na base de ensaio.

O servidor registrou WinError 10054 ao fechar uma conexão do navegador, como no ensaio anterior; não houve falha nos downloads ou perda de dados observada.

Capturas desktop e mobile emulado de 412 pixels refeitas. Conferência visual e teste de largura da página sem transbordamento. Celular físico não foi executado. Não foram executadas fórmulas em Excel/LibreOffice; a proteção é verificada na serialização, sem promessa sobre alterações posteriores em outros programas.

## Distribuição e compatibilidade

Versão 0.3.1, esquema 2 e dependências da 0.3.0 mantidos. Amostras originais preservadas. Os dados principais em data/ não foram usados como base de ensaio. Todos os arquivos, caches, ambientes, logs, capturas e entrega desta tarefa ficam no D:.

A cópia limpa em .cache/validacao031/RadarInflacao preparou o ambiente usando preparar.cmd e Python já disponível no D:. Importou 82 meses nacionais e 738 observações dos grupos; a segunda importação não duplicou dados. Exportou seis registros e abriu o painel dos grupos com três downloads via AppTest. A rota pip continua disponível; foi usada a rota uv existente nesta preparação.

Os CSVs completos dos grupos, do ranking e de duas comparações (uma com ausência histórica) foram confrontados com a versão 0.3.0 extraída da tag local, usando a mesma procedência fixa. Os quatro pares foram idênticos byte a byte; hashes registrados em .cache/compatibilidade031.log. A entrega fonte é conferida também após extrair o ZIP. Windows foi executado; Linux/macOS nativos não foram testados nesta etapa. O workflow Windows/Linux permanece preparado, sem execução remota. Nenhum serviço foi publicado, contratado ou agendado.

## Referências

- [Python: Decimal e copy_negate](https://docs.python.org/3/library/decimal.html#decimal.Decimal.copy_negate).
- [OWASP: CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection).
- [Streamlit: download_button e on_click](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button).
- [Altair: limite padrão de grandes conjuntos](https://altair-viz.github.io/user_guide/large_datasets.html).
- [Limites da publicação CSV já documentados](REVISAO-0.2.1.md).
