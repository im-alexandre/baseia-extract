---
id: technical.backlog.production-orchestration
title: "TODO ORC-001: orquestração de produção"
kind: backlog-item
audience: maintainer
mode: production
stage: orchestration
status: todo
nav_order: 594
---

# TODO ORC-001: orquestração de produção

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

Executar o pipeline de produção sem depender da coordenação manual contínua do
CLI local.

## Impacto atual

O Compose provisiona Temporal e o catálogo grava outbox, mas não existem
workflows ativos. O CLI Poe continua coordenando extract e render.

## Resultado que falta alcançar

- workflow durável para as stages suportadas;
- retomada e observabilidade de produção;
- integração com idempotência, leases e outbox existentes;
- separação clara entre orquestração e execução GPU;
- operação distribuída sem transformar S3 em fila.

## Fora deste TODO

Este registro não escolhe workflows, activities, filas, políticas de retry nem
topologia Temporal.

Anterior: [OPS-001 — Estratégia promovível](promotable-strategy.md)
Próximo: [Guia de desenvolvimento](../development/guide.md)
Operação relacionada: [Executar em produção](../../operational/production/execute-pipeline.md)
