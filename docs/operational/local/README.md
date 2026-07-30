---
id: operational.local.home
title: Execução local
kind: index
audience: user
mode: local
stage: navigation
status: current
nav_order: 100
---

# Execução local

[Documentação](../../README.md) · [Uso](../README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

O ambiente local prioriza rapidez para inventariar, amostrar, experimentar e
inspecionar documentos. A coleção permanece no path informado; configuração,
inventários e relatórios ficam em `baseia.collection.yaml` e `.baseia/` junto
da fonte, não dentro do repositório.

PostgreSQL e S3 não são necessários para inventário, amostragem, render ou
auditoria. Eles também não são proibidos: o mesmo modo local pode usar uma URL
MinerU em container, serviços externos ou um S3 de desenvolvimento quando isso
for conveniente.

A extração sempre precisa de um parser ou backend. O caminho integrado
atualmente usa uma URL MinerU com o contrato BaseIA. Essa URL pode estar no
host, em container ou em outro servidor.

## Percurso recomendado

1. [Quick Start](quickstart.md) — ciclo resumido;
2. [Instalação](installation.md);
3. [Primeiro inventário](inventory.md);
4. [Primeira amostragem](sampling.md);
5. [Primeira extração](extraction.md);
6. [Primeiro render](rendering.md);
7. [Auditoria e recuperação](audit-and-recovery.md).

## Default de workers

Os comandos paralelos usam três workers por padrão. Ajuste esse valor conforme
os recursos locais ou, no extract, conforme a capacidade dos serviços MinerU
usados. A semântica técnica ainda precisa ser unificada; consulte o
[TODO de concorrência e capacidade](../../technical/backlog/concurrency-model.md).

Anterior: [Utilização do BaseIA](../README.md)
Próximo: [Quick Start](quickstart.md)
Avançado: [Modos de execução](../../technical/architecture/overview.md)
