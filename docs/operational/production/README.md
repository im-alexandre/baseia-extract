---
id: operational.production.home
title: Produção
kind: index
audience: operator
mode: production
stage: navigation
status: current
nav_order: 300
---

# Produção

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

Produção aplica uma estratégia aprovada a registros novos. Não importa runs,
task IDs, tentativas, manifests experimentais nem snapshots de
desenvolvimento.

## Percurso recomendado

1. [Promover a estratégia](promoting-the-strategy.md);
2. [Levantar o ambiente de referência](compose-environment.md);
3. [Registrar, executar e ativar a coleção](collection-bootstrap.md);
4. [Executar e retomar o pipeline](execute-pipeline.md);
5. [Substituir serviços por endpoints externos](external-services.md);
6. [Operar e recuperar](operations.md).

O [runbook da coleção inicial](initial-corpus-runbook.md) é histórico e
específico deste repositório. Novas coleções usam `poe init` e
`poe pipeline`.

## Estado implementado

- registro e alternância de coleções;
- inventário e amostragem externos ao worktree;
- extração MinerU idempotente;
- render canônico;
- revisão somente leitura de metadados canônicos;
- chunks estruturais, embeddings OpenRouter e ingestão idempotente no Qdrant;
- auditorias entre etapas;
- promoção genérica para S3 e catálogo;
- múltiplas URLs MinerU e stores externos.

O CLI Poe ainda coordena as etapas. Temporal, estratégia promovível
formalizada e exportação de dumps de cliente permanecem futuros.

Anterior: [Desenvolvimento catalogado](../cataloged-development/README.md)
Próximo: [Promover a estratégia](promoting-the-strategy.md)
Avançado: [Visão geral da arquitetura](../../technical/architecture/overview.md)
