# Demonstração offline — IPCA × INPC

A versão 0.7.0 inclui um HTML autossuficiente do comparador nacional. Para quem recebe a demonstração, basta extrair o ZIP e abrir `ABRIR-DEMONSTRACAO.html` no navegador com JavaScript habilitado. Python, instalação de dependências, servidor e internet não são necessários para explorar o arquivo.

## Testar direto no navegador

**[Abrir o Radar da Inflação no GitHub Pages](https://luizcodebr.github.io/RadarInflacao/)**. Escolha o período e o indicador para explorar os gráficos e baixar o CSV, sem instalar nada.

A página precisa de internet para carregar. Depois de carregada, filtros, gráficos e exportação são processados no próprio navegador, sem novas consultas ao IBGE. A amostra continua fixa até outubro/2026. Para abrir novamente sem depender de internet, guarde o ZIP conforme as instruções abaixo. [Como a publicação no Pages funciona](PAGES.md).

## Baixar e abrir

1. [Baixe RadarInflacao-Demo-0.7.0.zip](https://github.com/LuizCodeBR/RadarInflacao/releases/download/v0.7.0/RadarInflacao-Demo-0.7.0.zip).
2. Salve no D: ou em uma pasta de sua escolha e extraia o ZIP (**Extrair Tudo** no Windows).
3. Abra a pasta extraída e dê dois cliques em `ABRIR-DEMONSTRACAO.html`.

Escolha os meses e o indicador. O botão **Baixar CSV do período** exporta os dados filtrados; para guardar o CSV no D:, escolha essa unidade ao salvar. O pacote contém somente HTML e instruções. O arquivo `Source code` oferecido pelo GitHub contém o projeto para desenvolvimento; para experimentar sem Python, escolha o ZIP da demonstração indicado acima.

## O que experimentar

- Escolher mês inicial, final e indicador: mensal, acumulado no ano ou em 12 meses.
- Usar os atalhos de 12 meses finais da amostra e histórico completo.
- Conferir os dois gráficos e detalhar um mês pelo seletor, teclado ou clique/toque no gráfico.
- Consultar a tabela e baixar CSV do período, com todas as três medidas e procedência.
- Consultar cobertura, fontes, datas originais e SHA-256 das respostas incluídas.

A amostra vai de janeiro/2020 a outubro/2026 (82 meses por índice). No mês de outubro/2026, a variação mensal é IPCA 0,14%, INPC 0,22% e diferença INPC − IPCA de +0,08 p.p. Em 12 meses, são 4,63%, 4,49% e −0,14 p.p.

O intervalo inclui seus dois limites. Inverter início/fim oculta os resultados anteriores e bloqueia o download até a correção; a escolha do indicador é preservada. Os cartões mostram o último mês do recorte, identificado na tela. O seletor Detalhar mês acompanha o destaque na tabela e nos gráficos.

## Dados e CSV

O gerador lê apenas `sample/` e `sample/inpc/`, verificando hashes, metadados, URLs exatas, datas, medidas, cobertura e continuidade pelos validadores já usados no aplicativo. Não abre o banco principal. Amostras com coberturas diferentes, meses ausentes ou duplicados são recusadas; o gerador não reduz silenciosamente o período.

Os acumulados são os oficiais de cada mês. Os filtros não recalculam janelas e não somam taxas. As diferenças são calculadas em Decimal no Python. A interface usa rótulos preparados pelo formatador existente; as coordenadas dos gráficos usam números do navegador, sem alterar os dados exportados.

O CSV usa o mesmo `index_csv_bytes` do comparador completo. O HTML guarda o cabeçalho e as linhas já serializadas; o navegador apenas seleciona as linhas do filtro e acrescenta o BOM UTF-8. O separador é ponto e vírgula, decimal com vírgula e fim de linha CRLF. O indicador escolhido afeta a visualização; o CSV sempre inclui as três medidas, conforme indicado junto ao botão.

O UUID da coluna Coleta ID é derivado de índice, hash e data original da amostra, para permitir gerar novamente arquivos idênticos. Ele identifica a amostra validada, não uma nova requisição, nem uma execução registrada no banco pessoal. Modo Amostra, data original e hash permanecem explícitos.

## Gerar novamente

Somente quem desenvolve precisa do ambiente Python do projeto. Para gerar um arquivo novo, sem sobrescrever destino existente:

```powershell
.\.venv\Scripts\python.exe -m radar_inflacao demo-html --output .cache\nova-demonstracao.html
```

O comando recusa `--data-dir`, porque essa entrega pública usa exclusivamente as amostras. O resultado não depende de uma base de usuário e não faz chamadas de rede.

Para preparar um ZIP de HTML + instruções em uma pasta ainda inexistente:

```powershell
.\.venv\Scripts\python.exe scripts\package_demo.py --output-dir D:\Projetos\Entregas\RadarInflacao-Demo-0.7.0
```

A pasta contém HTML, LEIA-ME, ZIP, SHA256SUMS e identificação da entrega. O ZIP contém somente HTML e LEIA-ME. Seus metadados de data são fixos para tornar a geração reproduzível; as datas efetivas das fontes permanecem no HTML. O pacote funciona em qualquer pasta/unidade gravável, sem caminhos do computador de desenvolvimento.

## Testes

[Resultados e limites da validação da versão 0.7.0](VALIDACAO-0.7.0.md).

`testar.cmd` inclui os testes de amostras, cobertura, precisão, CSV, isolamento da geração e ZIP. O teste de navegador é opcional e precisa de Node/Playwright já disponíveis no computador de desenvolvimento. Para torná-lo obrigatório, configure `RADAR_REQUIRE_BROWSER=1` e `RADAR_PLAYWRIGHT_MODULE` com o caminho do módulo Playwright instalado. `PLAYWRIGHT_BROWSERS_PATH` pode selecionar navegadores existentes no D:.

O ensaio abre `file://` em uma pasta com espaços e desliga a rede. Confere filtros, todas as medidas, valores do exportador original, dados completos, mês único, diferenças positivas/negativas/zero, intervalo invertido, navegação por teclado, gráficos e downloads. Compara nove CSVs byte a byte e verifica larguras de 1440, 390 e 320 pixels. Perfis, temporários e downloads ficam na pasta de teste. O ZIP não contém Node, Playwright ou testes.

## Limites

A demonstração é uma fotografia das amostras, sem coleta nova, banco, grupos, áreas ou comparação A/B. Para esses recursos, use o aplicativo completo. A atualização do exemplo ocorre pela regeneração do HTML com novas amostras verificadas, não ao abrir o arquivo.

CSS, JavaScript e dados estão incorporados: não há fontes, bibliotecas ou recursos externos carregados automaticamente. Links para IBGE e GitHub exigem internet apenas se a pessoa decidir abri-los. A política do documento bloqueia conexões, objetos e fontes de recursos externas.

A demonstração não grava configurações nem dados no navegador. O destino do CSV e os arquivos próprios do navegador seguem as configurações dele; para salvar o CSV no D:, selecione a unidade na janela de download. Os arquivos do projeto, geração e testes desta entrega ficam no D:.
