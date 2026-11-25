# CLAUDE.md

## Commits locais

Commit que não foi para o remoto não existe. O container desta sessão pode ser
reconstruído a qualquer momento, e o repositório volta clonado do remoto — um
commit só local some junto, e o reflog não alcança.

Quando houver motivo para não subir na branch de produção (um deploy que
precisa esperar uma migração de dados, por exemplo), suba numa branch separada
em vez de deixar só no container. Preserva o trabalho sem disparar o deploy.

## Testes de mutação

Nunca use `git checkout` em arquivos que tenham alterações não commitadas. O
`checkout` restaura o arquivo a partir do HEAD e descarta em silêncio tudo que
ainda não foi commitado — numa rodada de mutação, isso apaga a própria correção
que você está testando, e a suíte volta a passar como se nada tivesse
acontecido.

Antes de mutar: faça `git commit` ou `git stash` das alterações pendentes.
Depois de restaurar: confira com `git status` que a árvore está como esperado,
e confirme que as definições que você tocou continuam no arquivo — `grep` por
um nome de função casa também com as chamadas, então procure pela definição
(`^def nome`), não pelo nome solto.
