---
id: technical.backlog.promotable-strategy
title: "TODO OPS-001: estratégia promovível"
kind: backlog-item
audience: maintainer
mode: production
stage: promotion
status: todo
nav_order: 593
---

# TODO OPS-001: estratégia promovível

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

Representar explicitamente as decisões funcionais aprendidas em
desenvolvimento que devem ser reaplicadas em produção.

## Impacto atual

A promoção é uma checklist manual. Isso preserva a separação de ambientes, mas
deixa implícito quais versões, parsers, configurações e critérios formam a
estratégia aprovada.

## Resultado que falta alcançar

- representação versionável da estratégia;
- separação entre escolhas funcionais e topologia/capacidade do ambiente;
- validação antes de executar produção;
- proveniência suficiente para reproduzir entregáveis;
- promoção sem carregar runs, tentativas ou manifests experimentais.

## Fora deste TODO

Este registro não determina formato, armazenamento, CLI nem integração com o
catálogo.

Anterior: [CAT-001 — Bootstrap genérico](generic-collection-bootstrap.md)
Próximo: [ORC-001 — Orquestração](production-orchestration.md)
Operação relacionada: [Promover a estratégia](../../operational/production/promoting-the-strategy.md)
