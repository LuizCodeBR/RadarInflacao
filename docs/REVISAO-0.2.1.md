# Revisão de segurança e concorrência — 0.2.1

16/11/2026, horário de São Paulo. Projeto: D:/Projetos/RadarInflacao. Revisão realizada pelo assistente sobre a versão 0.2.0, com nova leitura do código e testes adversos. Não é certificação de segurança, auditoria humana externa ou teste de invasão de hospedagem.

## Escopo e modelo de uso

Comparações, formatação decimal, exportação mensal/comparativa, publicação de CSV pela CLI, downloads no navegador e acesso concorrente ao banco local. Interface limitada a 127.0.0.1; dados públicos, sem login ou credenciais.

O fluxo normal restringe valores e procedência: taxas são validadas na coleta; data de consulta, UUID e hash são gerados ou verificados pelo pipeline. Não foi identificado neste escopo um caminho de entrada remota de fórmulas pelo IBGE. Os testes de CSV com textos hostis simulam corrupção da base local ou utilização direta dos exportadores com dados inválidos.

## Achados e correções

| Achado | Evidência e consequência | Correção |
| --- | --- | --- |
| Precisão dependente do contexto no CSV mensal | Decimal.normalize() sob precisão 3 transformava 0,123456 em 0,123; com sinalização restritiva podia lançar erro | Conversão decimal sem operação de arredondamento; remoção textual de zeros finais |
| Contexto decimal parcialmente isolado | localcontext() copiava limites e traps do chamador; a apresentação de 1,234 podia falhar com Inexact habilitado | Contexto explícito por cálculo, com precisão, limites, arredondamento e sinais definidos; contexto externo preservado |
| Ausência de validação na fronteira CSV | Texto =1+1 em procedência alterada era exportado como célula potencialmente interpretável como fórmula | Campos tipados: mês, taxas finitas, modo, data ISO com fuso, SHA-256 e UUID; descrições rejeitam prefixos de fórmula e controles |
| Arquivo final criado antes da serialização/gravação terminar | Exportação podia deixar destino vazio após erro de serialização, ou parcial após falha de escrita | Serializar primeiro; gravar temporário no mesmo diretório, flush/fsync e publicar por link atômico sem sobrescrita |
| Clique no download disparava uma nova execução do painel | Comportamento padrão do Streamlit podia reler base atualizada ou ocupada após preparar o arquivo da tela anterior | on_click="ignore" nos dois downloads; bytes pertencem à consulta exibida, com orientação para atualizar a página |

A proteção de texto não prefixa taxas negativas com apóstrofos: os números são gerados exclusivamente de Decimal validado. Os textos que falham são recusados; o dado original não é silenciosamente alterado. Aspas e separadores são tratados pelo módulo csv. Uma procedência mensal inválida mostra mensagem no painel e impede esse download, sem derrubar a comparação de valores válidos.

## Concorrência e publicação

O bloqueio existente no repositório continua coordenando os acessos. Um escritor em outro processo foi interrompido dentro de uma transação: nova consulta recebeu BusyError, a comparação anterior manteve os dados antigos e a consulta após COMMIT recebeu os dados novos. Nenhuma composição misturou as duas versões nesse cenário.

Dois processos prepararam conteúdos diferentes e disputaram o mesmo caminho de exportação. Um publicou; outro recebeu FileExistsError. O arquivo final continha exatamente um dos conteúdos completos. Não foi usado os.replace(), que substituiria o destino vencedor.

O temporário é criado no diretório de destino com nome aleatório e removido em falhas tratadas. Os bytes são sincronizados antes de os.link(). Falhas de fsync ou falta de suporte a links não publicam o arquivo final. O caminho existente continua protegido contra sobrescrita.

Requisito: sistema de arquivos local com suporte a hard links, validado no disco D: deste computador. NTFS e sistemas Linux usuais atendem; volumes sem suporte, como alguns removíveis, podem recusar a exportação pela CLI. O download pelo navegador não usa essa operação. Uma interrupção abrupta pode deixar .radar-csv-*.tmp; não há promessa de durabilidade absoluta diante de falha física ou queda de energia. Não se deve usar pasta compartilhada ou sincronizada como banco concorrente.

## Resultados dos testes

- Windows / Python 3.13.14: **144 testes aprovados**, 20,50 s; Ruff aprovado.
- Windows / Python 3.12.13: **144 testes aprovados**, 20,57 s.
- 52 casos novos além dos 92 da versão 0.2.0.
- Regressões iniciais reproduziram falhas de contexto decimal e ausência de recusa de campos hostis antes das correções.
- Casos novos incluem fórmulas com =, +, -, @, espaços, variante Unicode, tabulação, CR/LF, aspas/separadores e NUL; tipos inválidos, expoentes excessivos, negativos preservados, falha antes da publicação e disputa entre processos.
- Testes da interface verificam tratamento de procedência inválida e downloads sem nova execução.

As contagens não representam percentual de cobertura ou ausência universal de falhas.

## Navegador real

Servidor de ensaio em 127.0.0.1:8504, base separada .cache/browser-021. Nenhum dado da pasta principal data/ foi modificado pelos ensaios.

1. Primeira sessão abre janeiro–março/2024 contra janeiro–março/2023 e baixa ambos os CSVs.
2. Outro processo altera a taxa de março na base exclusiva de ensaio.
3. Durante um lock mantido por outro processo, a sessão inicial baixa arquivos idênticos byte a byte aos anteriores, sem trocar o indicador exibido.
4. Segunda sessão lê a taxa nova e gera CSV diferente.
5. A alteração sintética é revertida na base de ensaio.
6. Capturas desktop/mobile atualizadas; largura de 412 pixels emulada, sem transbordamento da página.

Não foram executadas fórmulas em Excel/LibreOffice. A verificação confirma sua recusa na serialização, sem promessa sobre transformações posteriores feitas em outros programas.

## Distribuição e limites

Versão 0.2.1, dependências existentes, esquema 1 e amostra preservados. Windows validado; Linux/macOS nativos e celular físico não foram executados nesta etapa. CI preparado, sem execução remota. ZIP fonte e documentação no D:, sem recursos pagos, nuvem ou agendamentos.

A consistência vale para operações que respeitam o protocolo de bloqueio da aplicação. Um programa externo que edite o banco ignorando esse protocolo não está coberto. O CSV representa a consulta que o preparou; ele não acompanha automaticamente atualizações posteriores.

## Referências

- [OWASP: CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection).
- [Python: contextos e operações Decimal](https://docs.python.org/3/library/decimal.html).
- [Python: os.link](https://docs.python.org/3/library/os.html#os.link).
- [Streamlit: download_button e on_click](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button).
