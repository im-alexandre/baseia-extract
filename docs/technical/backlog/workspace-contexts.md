---
id: technical.backlog.workspace-contexts
title: "TODO CTX-001: workspaces e perfis de recursos"
kind: backlog-item
audience: maintainer
mode: all
stage: context
status: todo
nav_order: 593
---

# TODO CTX-001: workspaces e perfis de recursos

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

Hoje cada coleção repete seu modo, escopo, topologia e referências de serviço.
O registro global permite alternar coleções, mas não agrupa defaults
compartilhados.

Um workspace futuro deve permitir perfis como:

- pessoal: storage, banco e Qdrant particulares;
- operador: infraestrutura compartilhada mantida pelo consultor;
- cliente: recursos isolados e futura exportação de dumps.

## Resultado esperado

- defaults herdáveis sem fundir identidades de coleção;
- override explícito por coleção;
- seleção de workspace + coleção na CLI;
- separação de credenciais por nomes de variáveis/secret store;
- migração compatível dos YAMLs atuais;
- estado observável de várias coleções por ambiente.

## Restrições

Workspace não pode virar diretório obrigatório dentro do repositório, catálogo
paralelo ou fonte de segredos. Coleção continua sendo a unidade de identidade
e snapshot.

Anterior: [CAT-001 concluído](generic-collection-bootstrap.md)
Próximo: [CAT-002 — Autoridade](production-authority-handoff.md)
Operação relacionada: [Coleções](../../operational/reference/commands.md#contexto-de-colecao)
