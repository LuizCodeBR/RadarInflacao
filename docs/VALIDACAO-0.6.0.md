# Validação — Radar da Inflação 0.6.0

Implementação do comparador nacional IPCA × INPC, com amostra oficial, histórico, central, gráficos, períodos e CSV. Arquivos no D:. Nenhum recurso pago, conta ou dependência adicional.

## Fonte real

Amostra INPC obtida pela API oficial, validada e preservada em sample/inpc. 82 meses, janeiro/2020–outubro/2026. Mensal/no ano/12 meses obrigatórios. SHA-256 dos dados be482bcbe6796d90713755ae1a284c6bb744228534ffcd5f46f0fdf22fadf0d7; 4588 bytes. Data/URLs/hash dos metadados no manifesto.

Em base isolada, importação da amostra, atualização real incremental (24 reconferências) e integral (82), sem mudanças fictícias nem duplicações. Qualidade INPC aprovada. Evidência .cache/coleta-real060.log. As amostras IPCA/grupos/áreas não foram atualizadas nesta etapa.

## Preservação

Cópia anterior de data sob bloqueio em .cache/antes-migracao060, com hashes .cache/principal060-antes.json. Migração 4→5 comparou todas as linhas das tabelas anteriores por serialização, excluindo somente a nova entrada de baseline INPC. Valores, tentativas e histórico antigos foram preservados.

A instalação principal continua com 82 nacionais IPCA, 738 dos grupos e 1394 regionais; recebeu 82 INPC e 246 inclusões. Os avisos anteriores de disponibilidade nacional/grupos permanecem, pois não houve coleta desses conjuntos. Áreas e INPC com qualidade aprovada. Evidência .cache/migracao060.log.

## Verificações

- Suíte completa Windows/Python 3.13.14: **490 aprovados**, 413,67 s; Ruff aprovado.
- Suíte completa Windows/Python 3.12.13: **490 aprovados**, 418,28 s.
- 420 casos anteriores preservados, 62 casos em tests/test_indices.py e 8 cenários HTTP existentes aplicados também ao novo coletor (total 490).
- Contratos próprios do INPC, unidade, nível/identificação Brasil, meses, três variáveis, ausências recusadas, não finitos, IDs IPCA indevidos e metadados divergentes.
- Importação/reimportação, incremental, histórico exato antes/depois e falhas na coleta/publicação com rollback de valores e eventos.
- Diferenças INPC − IPCA exatas, sinais/zero/negativos, fontes distintas, contexto decimal restritivo, CSV com BOM/separador/CRLF e recusa de objetos comparativos incoerentes.
- Migração 4→5 preserva todos os conjuntos anteriores; falha da migração desfaz as tabelas novas.
- Interface: filtros, medidas, A/B manual, durações diferentes, sobreposição, comparação B indisponível, cobertura divergente e origem corrompida com erro controlado.
- Dois processos reais: escritor INPC pausado após as escritas e antes do commit; leitura nova recebe BusyError. Os dois CSVs preparados permanecem idênticos. Commit confirma alteração/histórico; morte do processo desfaz ambos e a tentativa vira INTERRUPTED. IPCA permanece intacto.

A inspeção das capturas encontrou um campo contendo pontos no nome, que gerava barras vazias apesar dos dados corretos. O campo e o tooltip receberam escape explícito para o Vega-Lite; a regressão confere essa referência. O teste final do navegador verifica 24 marcas de barra e alturas não nulas no recorte padrão, inclusive no celular. Os 62 casos afetados foram repetidos nos dois Python após a correção visual: 62 aprovados em 35,83 s (3.13) e 62 em 41,97 s (3.12).

As duas suítes completas usaram diretórios independentes e rodaram simultaneamente; os tempos não são comparativo de desempenho. Resultados detalhados em .cache/testes060-313.log, testes060-312.log, indices060-final313.log e indices060-final312.log.

A primeira bateria direcionada encontrou um valor esperado incorreto no teste de 12 meses: 4,49 − 4,63 = −0,14 p.p. A expectativa foi corrigida e a bateria final passou. A primeira automação de download acionou o botão antes de concluir a aplicação do segundo filtro; o roteiro final aguarda o recorte aplicado visível antes de baixar.

Navegador final: gráficos, medidas, dois CSVs, filtros, ano anterior, intervalo invertido e desktop/celular emulado sem transbordamento. Capturas atualizadas e inspecionadas. Evidência .cache/navegador060-final.log. O roteiro usa o Playwright/Chromium já existentes em outro projeto; não são dependências do Radar.

Instalação limpa com preparar.cmd no D: e Python 3.13. Importação de quatro amostras e repetição sem duplicar os 7626 eventos. Dois CSVs do comparador, qualidade com 16 verificações, histórico INPC com 246 inclusões, CLI sem sobrescrita e painel foram conferidos. Logs .cache/instalacao060.log e instalacao060-smoke.log.

## Distribuição

Pacote fonte em D:/Projetos/Entregas/RadarInflacao-0.6.0/RadarInflacao-0.6.0-fonte.zip, com código, testes, amostras oficiais, documentação e capturas. Exclui data, ambientes, caches, exportações e Git. A entrega inclui SHA-256 e identificação do commit/tag local. Validação do conteúdo extraído em .cache/pacote060.log.

O repositório continua sem remoto configurado; não houve publicação online. O servidor temporário da verificação usa base separada e é encerrado ao concluir. Nenhuma ferramenta nova precisa ser instalada neste computador.

## Limites

Validação local Windows. CI Windows/Linux continua configurada, sem execução remota nesta etapa. Não houve teste nativo Linux/macOS, aparelho celular físico ou abertura no Excel/LibreOffice. Não há hospedagem nem aplicação mobile nativa.

Publicações por conjunto independentes; leituras/escritas cooperam pelo bloqueio local. Disco de rede/sincronizado ou programas externos que ignorem o bloqueio estão fora do contrato. Histórico/hashes não são assinatura contra adulteração do disco. Não se afirma durabilidade contra toda falha física.

[Guia do comparador](INDICES.md) · [Arquitetura](ARQUITETURA.md).
