---
id: technical.backlog.qdrant-ingestion
title: "ING-001: chunking, embeddings e Qdrant"
kind: backlog-item
audience: maintainer
mode: all
stage: ingest
status: deprecated
nav_order: 598
---

# ING-001: chunking, embeddings e Qdrant

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Histórico

Este item foi concluído e mantido apenas para preservar o histórico do backlog.
A implementação vigente está em [Ingestão e retrieval](../concepts/ingestion.md).

## Resultado entregue

O estágio `ingest` prepara chunks estruturais locais por política YAML e, em
`apply`, usa OpenRouter e LangChain-Qdrant para materializar pontos
idempotentes no Qdrant. A reconciliação valida dimensão e distância, faz
upsert pelos IDs determinísticos e remove pontos obsoletos do mesmo documento e
perfil quando a política permite substituição.

Anterior: [ORC-001 — Orquestração](production-orchestration.md)
Próximo: [Ingestão e retrieval](../concepts/ingestion.md)
Operação relacionada: [Produção](../../operational/production/README.md)
