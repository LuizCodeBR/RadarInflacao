# Acompanhar o feedback

Os formulários **Enviar sugestão** e **Relatar problema** do Radar aplicam etiquetas automaticamente quando a pessoa cria a mensagem no GitHub.

| Formulário | Tipo aplicado | Situação inicial |
| --- | --- | --- |
| Enviar sugestão | `enhancement` — sugestão de melhoria | `triagem` — aguardando análise |
| Relatar problema | `bug` — algo não funcionou como esperado | `triagem` — aguardando análise |

As etiquetas `enhancement` e `bug` já existiam no repositório e foram mantidas, com descrições em português. A etiqueta amarela `triagem` permite localizar rapidamente o que ainda precisa ser analisado.

## Links para acompanhar

- [Feedback aguardando análise](https://github.com/LuizCodeBR/RadarInflacao/issues?q=is%3Aissue%20is%3Aopen%20label%3Atriagem).
- [Sugestões abertas](https://github.com/LuizCodeBR/RadarInflacao/issues?q=is%3Aissue%20is%3Aopen%20label%3Aenhancement).
- [Problemas abertos](https://github.com/LuizCodeBR/RadarInflacao/issues?q=is%3Aissue%20is%3Aopen%20label%3Abug).

Os filtros mostram apenas mensagens abertas. Um resultado vazio significa que ainda não há mensagens nessa categoria.

## Rotina de acompanhamento

1. Abra **Feedback aguardando análise** e leia as novas mensagens.
2. Depois de analisar, remova `triagem` e mantenha a etiqueta do tipo. Se necessário, ajuste entre `enhancement` e `bug`.
3. Use os comentários da mensagem para acompanhar a conversa e feche a mensagem quando ela estiver resolvida ou concluída.

A classificação inicial é feita pelo próprio GitHub, pelo campo `labels` dos arquivos `.github/ISSUE_TEMPLATE/sugestao.yml` e `.github/ISSUE_TEMPLATE/problema.yml`. Não precisa de aplicação, rotina agendada, chave adicional ou serviço pago. As etiquetas precisam continuar existindo com esses nomes no repositório.

Envios fora desses dois formulários podem ser classificados manualmente com as mesmas etiquetas. A retirada de `triagem` após a análise é manual; fechar uma mensagem também a retira das listas de pendências acima. A etiqueta de tipo é mantida para consulta do histórico.

A configuração dos formulários e este guia ficam em `D:\Projetos\RadarInflacao`. Os registros da configuração ficam em `.cache/feedback070`, dentro do projeto no D:. Não havia mensagens de feedback para classificar no momento desta configuração.
