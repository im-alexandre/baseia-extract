---
id: technical.backlog.qdrant-ingestion
title: "TODO ING-001: chunking, embeddings e Qdrant"
kind: backlog-item
audience: maintainer
mode: all
stage: ingest
status: todo
nav_order: 598
---

# TODO ING-001: chunking, embeddings e Qdrant

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

Consumir artefatos canônicos persistidos, gerar chunks e embeddings e
materializá-los em uma coleção Qdrant sem depender de paths locais.

## Contrato de entrada esperado

O mock ou implementação futura deve receber referências inequívocas a:

- coleção, documento e revisão;
- snapshot ativo;
- `canonical/document.md`, IR e estrutura;
- checksums e versão da estratégia;
- política de chunking e modelo de embedding.

## Resultado que falta

- schema de chunk e identidade vetorial;
- adapter de embeddings;
- writer Qdrant idempotente;
- auditoria e reconciliação;
- inclusão da stage `ingest` no pipeline;
- exportação/dump para entregas de cliente.

Enquanto este item estiver aberto, `pipeline --through ingest` falha
explicitamente e `qdrant_url` é apenas reserva de configuração.

Anterior: [ORC-001 — Orquestração](production-orchestration.md)
Próximo: [Índice técnico](../README.md)
Operação relacionada: [Produção](../../operational/production/README.md)
