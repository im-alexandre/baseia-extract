---
id: operational.cataloged.promotion
title: Preparar a estratégia para produção
kind: how-to
audience: operator
mode: cataloged-development
stage: promotion
status: current
nav_order: 250
---

# Preparar a estratégia para produção

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Dev catalogado](README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

O desenvolvimento catalogado preserva evidência dos experimentos. Produção
reutiliza a estratégia aprovada, não esse histórico operacional.

## Promova como estratégia

Registre fora do histórico de runs:

- parser e versão;
- backend e opções de OCR;
- regras de render e versão;
- critérios de auditoria aceitos;
- topologia e requisitos de capacidade;
- política de chunking/embedding quando essa etapa existir.

## Não promova automaticamente

- task IDs, tentativas, leases e owners;
- logs, duração, pods e URLs temporárias;
- manifests ou snapshots experimentais;
- credenciais;
- artefatos de amostras que não façam parte da entrega.

## Iniciar produção

No diretório limpo de entrega, execute um novo `poe init` em modo
`production`. Isso recria inventário e manifestos. Depois valide localmente,
promova o snapshot S3 e trate esse inventário S3 como autoridade.

O campo `strategy` do YAML atual é um identificador mínimo (`name` e
`version`). Um pacote de estratégia validado e promovível continua no
[soft backlog](../../technical/backlog/promotable-strategy.md).

Anterior: [Renderizar e publicar](rendering.md)
Próximo: [Produção](../production/README.md)
Avançado: [Promover a estratégia](../production/promoting-the-strategy.md)
