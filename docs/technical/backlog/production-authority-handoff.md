---
id: technical.backlog.production-authority
title: "TODO CAT-002: handoff inicial de autoridade para S3"
kind: backlog-item
audience: maintainer
mode: production
stage: inventory
status: todo
nav_order: 594
---

# TODO CAT-002: handoff inicial de autoridade para S3

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

O pipeline integrado promove o snapshot depois de extract e render. O modelo
de produção desejado também precisa suportar:

1. inventário limpo em disco;
2. upload apenas dos PDFs e manifesto inicial;
3. inventário independente do S3;
4. comparação integral de path, tamanho e SHA-256;
5. ativação do snapshot bruto;
6. abandono do inventário local como autoridade;
7. execução das stages a partir de referências do snapshot.

## Resultado esperado

- estados distintos para snapshot bruto e snapshot enriquecido;
- auditoria disco ↔ S3 antes da ativação;
- comandos retomáveis e idempotentes;
- nenhuma promoção de metadados de desenvolvimento;
- stage inputs resolvidos pelo catálogo/S3, não por path absoluto;
- política clara para documentos adicionados depois.

## Fora deste item

Não define orquestração Temporal nem ingestão Qdrant.

Anterior: [CTX-001 — Workspaces](workspace-contexts.md)
Próximo: [SEM-001 — Tipos semânticos](semantic-block-types.md)
Operação relacionada: [Bootstrap de produção](../../operational/production/collection-bootstrap.md)
