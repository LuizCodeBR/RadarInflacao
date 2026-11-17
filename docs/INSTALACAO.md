# Instalação e uso

## Neste computador

Python 3.13.14 gerenciado pelo uv já existente, instalado em D:\Ferramentas\Python\uv-managed. Ambiente em D:\Projetos\RadarInflacao\.venv. Nenhuma alteração permanente do PATH foi necessária.

Abra iniciar.cmd no projeto e acesse http://localhost:8501. Use Ctrl+C para encerrar. testar.cmd verifica estilo e testes; atualizar.cmd consulta o IBGE. Sem necessidade de instalar algo adicional para executar esta entrega.

## Outra máquina Windows

Instale Python 3.12 ou 3.13 pelo distribuidor de sua escolha, selecionando uma pasta gravável e o D: se quiser manter o mesmo padrão. Extraia o projeto em D:\Projetos\RadarInflacao e execute iniciar.cmd. Pode indicar o executável com -Python 'caminho\python.exe' no preparar.cmd.

O iniciador cria .venv, instala os requisitos fixados e o próprio pacote em modo editável. A primeira instalação precisa de internet. Depois, um registro dos hashes dos requisitos evita reinstalar em cada abertura. Se mudar as dependências, a preparação é refeita.

A execução Windows utiliza PowerShell com liberação de execução só nesse processo; não altera a política permanente. uv é aproveitado quando já existe, mas não é obrigatório. Python/venv/pip bastam. -UsarPip permite testar o caminho de instalação convencional.

O Python não é incluído no ZIP. Não se promete um executável independente do interpretador.

## VS Code

Abra a pasta do projeto. Se usar a extensão Python da Microsoft, selecione .venv/Scripts/python.exe como interpretador; a configuração da pasta já indica esse caminho no Windows. Essa extensão ajuda a editar e depurar, mas não é necessária para usar os iniciadores. Nenhuma extensão foi instalada automaticamente.

## Modo sem consulta à internet

O painel inicial importa a amostra local se a base estiver vazia e a identifica explicitamente. Alterar filtros não consulta a API. É possível testar a instalação com rede indisponível depois de preparar as dependências.

Não confunda amostra offline com dados atualizados ao abrir. O momento de obtenção acompanha os dados.

## Bases independentes

RADAR_DATA_DIR aponta para outra pasta. Na CLI, use --data-dir antes do comando. Não compartilhe um arquivo de banco entre aplicações que ignorem o protocolo de lock.

Banco, respostas brutas e histórico ficam juntos. Com o aplicativo encerrado, preserve essa pasta para guardar o estado; a entrega inicial não inclui rotina de backup automatizado.

## Linux/macOS

Use Python 3.12/3.13, venv e pip. Execute bash iniciar.sh ou bash testar.sh. RADAR_PYTHON seleciona o executável quando python3 não for a versão desejada. Caminhos e caches ficam na pasta do projeto.

Esses iniciadores têm sintaxe conferida; a execução nativa Linux/macOS depende da validação no respectivo ambiente. O workflow de CI está preparado no repositório local, sem alegação de execução remota nesta entrega.


## Atualização para 0.3.0

Mesmas dependências. O painel oferece Índice geral e Grupos de despesas. A pasta sample/groups acompanha o ZIP e permite testar a nova área offline após preparar o ambiente.

O banco migra do esquema 1 para 2 na primeira abertura, preservando as observações e o histórico nacionais. Não execute a versão antiga contra um banco já migrado. Antes de substituir uma instalação própria, com o aplicativo encerrado, preserve a pasta data para manter uma cópia compatível com a versão anterior.

atualizar.cmd atualiza os dois conjuntos; falhas são informadas separadamente. A CLI permite update --dataset groups ou --dataset national. Veja [guia dos grupos](GRUPOS.md).


## Atualização para 0.4.0

Nenhuma dependência ou extensão nova. Iniciar/testar/atualizar continuam iguais. A nova opção Qualidade e atualização fica no seletor Análise do painel. Depois da preparação inicial, a demonstração offline é ativada pelo próprio painel e usa .cache/quality-demo, sem rede ou conta.

O esquema migra de 2 para 3, em transação, preservando observações e tentativas existentes. Também é possível migrar de 1 para 3. Antes de atualizar sua instalação, com o aplicativo encerrado, preserve a pasta data. O código anterior recusa o esquema 3; para retornar a ele seria necessário restaurar uma cópia compatível.

Neste computador, foi criada uma cópia anterior do banco em D:/Projetos/RadarInflacao/.cache/antes-migracao040. A migração conservou 82 registros nacionais, 738 dos grupos e as tentativas anteriores, sem mudanças retrospectivas inventadas.

Novos comandos: quality, quality-export e quality-demo. Somente quality-demo usa a pasta fixa do exemplo e recusa --data-dir para impedir que o cenário seja criado sobre outra base. quality e quality-export aceitam a opção global --data-dir ou RADAR_DATA_DIR para consultar outra base. [Guia e exemplos](QUALIDADE.md).

## Atualização para 0.5.0

Mesmas dependências, sem extensão nova. A opção Comparar áreas prepara sua amostra na primeira abertura, sem rede. Atualizar pelo IBGE e atualizar.cmd incluem nacional, grupos e áreas. CLI permite restringir com --dataset areas. O banco migra para esquema 4; preserve data/ com o aplicativo encerrado antes de substituir outra instalação. Nesta máquina, a cópia anterior ficou em D:/Projetos/RadarInflacao/.cache/antes-migracao050. A migração preservou todos os conjuntos/históricos anteriores e acrescentou 1394 registros regionais. [Guia das áreas](AREAS.md).

## Atualização para 0.5.1

Encerre o painel e use o pacote completo da nova versão. Preserve a pasta data de sua instalação. Esta revisão usa o mesmo esquema 4 da 0.5.0 e não precisa migrar o banco. Python 3.12 ou 3.13, dependências fixadas e iniciadores permanecem; nenhuma extensão do VS Code ou serviço adicional é necessário.

No computador de desenvolvimento, a base principal foi preservada e os ensaios ocorreram em pastas separadas no D:. [Relatório da revisão](REVISAO-0.5.1.md).

## Atualização para 0.6.0

O comparador IPCA × INPC usa as mesmas versões de Python e dependências. Encerre o aplicativo, preserve data e substitua o pacote fonte completo. Ao abrir, o esquema migra de 4 para 5, adicionando apenas as tabelas do INPC. Código até 0.5.1 não abre esquema 5; guarde uma cópia compatível se precisar reverter.

Nesta máquina foi preservada a cópia D:/Projetos/RadarInflacao/.cache/antes-migracao060. Não exige extensão ou novo software. [Guia dos índices](INDICES.md) · [Validação](VALIDACAO-0.6.0.md).
