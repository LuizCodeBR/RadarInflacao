# Validação da demonstração offline 0.7.0

Validada em 18/11/2026 no Windows. Código, entrega, perfis do navegador, downloads e temporários desta atividade ficam no D:. Não foram contratados serviços nem instaladas novas dependências.

## Entrega

- ZIP: `D:\Projetos\Entregas\RadarInflacao-Demo-0.7.0\RadarInflacao-Demo-0.7.0.zip`
- Tamanho: 19.534 bytes.
- SHA-256: `c3d6330a43fd6ac670829fc13781e27aedd7bd61dad40b0ea2776396c80f4c21`.
- Conteúdo: uma pasta com `ABRIR-DEMONSTRACAO.html` e `LEIA-ME.txt`.
- O HTML da entrega, do ZIP e da raiz do projeto é idêntico. O pacote contém somente dados da amostra, sem banco pessoal ou dependências de execução.
- Amostra fixa: janeiro/2020 a outubro/2026, 82 meses em cada índice. Não consulta dados novos ao abrir.

## Resultados

| Verificação | Resultado |
| --- | --- |
| Testes novos da demonstração, Python 3.13 | 21 aprovados, incluindo navegador |
| Testes novos da demonstração, Python 3.12 | 21 aprovados, incluindo navegador |
| Suíte completa, Python 3.13 | 554 aprovados; 3 excederam o limite de tempo do painel Streamlit |
| Reexecução isolada de todo `test_app.py` | 6 aprovados em 33,44 s; inclui os 3 que excederam o tempo; limite original de 20 s mantido |
| Confirmação de gravação/interrupção e preparação concorrente, Python 3.12 | 3 aprovados em 7,46 s na execução isolada |
| ZIP final extraído em pasta com espaços, aberto por `file://` e com rede desligada | Aprovado |
| CSVs baixados pelo navegador no teste do ZIP | 9 idênticos, byte a byte, ao exportador do projeto |
| Requisições HTTP / erros JavaScript no teste do ZIP | 0 / 0 |
| Larguras verificadas | 1440, 390 e 320 pixels |
| Ruff; consistência do arquivo de dependências; `git diff --check` | Aprovados |
| Banco, arquivos brutos e amostras existentes | 20 arquivos conferidos por SHA-256; nenhuma alteração |

Todos os 557 casos da suíte tiveram resultado aprovado na execução completa ou na reexecução dos casos afetados. Não houve uma execução única com 557 aprovações: os três limites de tempo estão registrados acima. A execução isolada do painel teve duração máxima de 6,53 s por teste. A verificação complementar em Python 3.12 também precisou de repetição isolada após uma falha de inicialização de processo durante execução concorrente. Esses resultados não substituem uma matriz de CI para esta versão.

## Cobertura e correção dos testes

Os testes verificam integridade e origem das amostras, cobertura completa dos dois índices, precisão decimal, diferenças positivas/negativas/zero, rejeição de dados pessoais ou inconsistentes, geração sem banco/rede, prevenção de sobrescrita, conteúdo e reprodução do ZIP.

No navegador, foram conferidos todos os indicadores, quatro recortes (12 meses, histórico completo, três meses e mês único), período invertido, restauração do filtro, navegação pelo teclado, seleção no gráfico, cartões, tabela e exportações. As imagens finais foram inspecionadas: [desktop](imagens/offline-desktop.png) e [celular](imagens/offline-mobile.png).

Uma falha anterior da simulação de encerramento abrupto foi reproduzida no Windows: encerrar o lançador do ambiente Python podia deixar o processo escritor continuar ao receber o fim da entrada. Os testes agora exigem uma mensagem explícita para confirmar a gravação e usam `os._exit(73)` no próprio escritor para simular a interrupção, sem executar a limpeza do Python. As verificações de transação, exclusividade e preservação do histórico foram mantidas. A lógica de gravação do aplicativo não foi alterada.

## Reproduzir e consultar evidências

O [guia offline](OFFLINE.md) explica geração e configuração do teste de navegador. Os registros locais desta entrega ficam em `.cache/offline070/`: `full313-final.log`, `app-isolated-final.log`, `atomic-isolated312.log`, `baseline.json` e `zip-verificado/browser-result.json`. O último relatório se refere ao HTML extraído do ZIP entregue, não apenas a um arquivo criado durante o teste.

O teste de navegador usa Chromium headless já disponível no D:. Firefox, Safari e outras plataformas não foram executados nesta validação. O uso do HTML não depende de Playwright, Node ou Python. O destino de futuros CSVs e os arquivos internos do navegador seguem suas configurações; para guardar os CSVs no D:, escolha essa unidade ao salvar.
