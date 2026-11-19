# Demonstração no GitHub Pages

**[Abrir o Radar da Inflação](https://luizcodebr.github.io/RadarInflacao/)**

Abra o link, escolha o período e o indicador e use os gráficos, a tabela e o botão **Baixar CSV do período**. Não precisa baixar ZIP, instalar Python ou criar conta.

O site oferece a mesma demonstração 0.7.0, com 82 meses por índice, de janeiro/2020 a outubro/2026. A amostra não se atualiza ao abrir a página. A internet é necessária para carregar o HTML; os filtros e a exportação funcionam no navegador, sem consultar o IBGE. Para guardar uma cópia que possa ser aberta sem internet, use o [ZIP da versão 0.7.0](https://github.com/LuizCodeBR/RadarInflacao/releases/download/v0.7.0/RadarInflacao-Demo-0.7.0.zip).

## Publicação

O fluxo [Publicar demonstração no Pages](https://github.com/LuizCodeBR/RadarInflacao/actions/workflows/pages.yml), definido em `.github/workflows/pages.yml`, publica o arquivo `ABRIR-DEMONSTRACAO.html` da raiz como `index.html`. Somente esse HTML é enviado para o site; estilos, gráficos e dados já estão incorporados nele.

A publicação é disparada quando o HTML ou o fluxo de publicação muda na branch `main`. Também pode ser executada manualmente na aba Actions. Não há instalação de dependências nem geração de dados durante a publicação. O fluxo confere que o HTML enviado é igual ao arquivo do repositório e limita a retenção do pacote temporário a um dia.

Para atualizar a amostra, gere e valide um novo HTML conforme o [guia offline](OFFLINE.md), atualize o arquivo da raiz e envie a alteração para `main`. O Pages publicará essa nova cópia. Alterações apenas no código do gerador não regeneram automaticamente o HTML.

O endereço usa o domínio gratuito `github.io`, sem domínio contratado. GitHub Pages está disponível para repositórios públicos no plano gratuito, conforme a [documentação do GitHub](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages). O fluxo usa um executor padrão Ubuntu do repositório público.

Os arquivos locais continuam em `D:\Projetos\RadarInflacao`; temporários, perfis de navegador, screenshots e CSVs da conferência ficam em `.cache/pages070`, dentro desse projeto no D:. O ZIP publicado da versão 0.7.0 é preservado. Ao baixar um CSV pelo site, escolha o D: na janela de download se quiser guardá-lo nessa unidade.
