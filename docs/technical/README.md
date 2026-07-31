---
id: technical.home
title: Desenvolvimento do framework
kind: index
audience: maintainer
mode: all
stage: navigation
status: current
nav_order: 500
---

# Desenvolvimento do framework

[Documentação](../README.md) · [Uso](../operational/README.md) ·
[Local](../operational/local/README.md) ·
[Dev catalogado](../operational/cataloged-development/README.md) ·
[Produção](../operational/production/README.md) ·
[Referência operacional](../operational/reference/README.md)

Esta área é deliberadamente técnica e avançada. Ela descreve os contratos que
mantêm identidade, idempotência, persistência e artefatos coerentes entre os
modos de execução.

## Estrutura e desenvolvimento

- [Estrutura do repositório](repository-structure.md)
- [Guia de desenvolvimento](development/guide.md)
- [Manutenção da documentação](development/documentation.md)
- [Soft backlog técnico](backlog/README.md)

O backlog também registra, sem fingir implementação, as próximas fronteiras:
[workspaces e perfis](backlog/workspace-contexts.md),
[transferência de autoridade para S3](backlog/production-authority-handoff.md),
[tipos semânticos ainda não modelados](backlog/semantic-block-types.md) e
[orquestração de produção](backlog/production-orchestration.md). O histórico de
[ING-001](backlog/qdrant-ingestion.md) aponta para a ingestão já implementada.

## Arquitetura

- [Visão geral e modos de execução](architecture/overview.md)
- [Transações, idempotência e concorrência](architecture/catalog.md)
- [Persistência MinerU e decisão do patch](architecture/mineru-persistence.md)

## Conceitos e contratos

- [Modelo do pipeline](concepts/pipeline.md)
- [Catálogo, inventário e identidade](concepts/catalog.md)
- [Artefatos e layout](concepts/artifacts.md)
- [Ingestão e retrieval](concepts/ingestion.md)

Entrada operacional: [Quick Start local](../operational/local/quickstart.md)
Próximo: [Estrutura do repositório](repository-structure.md)
