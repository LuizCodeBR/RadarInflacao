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
