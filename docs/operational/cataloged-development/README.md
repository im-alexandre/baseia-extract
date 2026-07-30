---
id: operational.cataloged.home
title: Desenvolvimento catalogado
kind: index
audience: operator
mode: cataloged-development
stage: navigation
status: current
nav_order: 200
---

# Desenvolvimento catalogado

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Produção](../production/README.md) ·
[Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

Use este modo quando quiser a agilidade do CLI com persistência em catálogo e
S3. Os PDFs e o estado de trabalho continuam no diretório da coleção; o
snapshot promovido passa a ser a autoridade catalogada daquele escopo.

## Percurso

1. [Preparar o ambiente](environment.md);
2. [Registrar, inventariar e promover](inventory.md);
3. [Extrair com persistência](extraction.md);
4. [Renderizar e publicar canônicos](rendering.md);
5. [Preparar a estratégia para produção](promotion.md).

## O que muda em relação ao local

| Aspecto | Local | Dev catalogado |
| --- | --- | --- |
| fonte e `.baseia` | disco da coleção | disco da coleção |
| catálogo | opcional | PostgreSQL via Catalog API |
| payload durável | disco | S3 compatível após promoção |
| extração | URL MinerU | URL MinerU com persistência server-side |
| autoridade | inventário local | snapshot S3 ativo por coleção |

Containers continuam opcionais. Você pode executar catálogo/S3 no Compose e
usar MinerU externo, ou substituir qualquer endpoint pela configuração da
coleção.

Anterior: [Execução local](../local/README.md)
Próximo: [Preparar o ambiente](environment.md)
Avançado: [Arquitetura do catálogo](../../technical/architecture/catalog.md)
