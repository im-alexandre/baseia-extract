---
id: docs.home
title: Documentação BaseIA Extract
kind: index
audience: all
mode: all
stage: navigation
status: current
nav_order: 0
---

# Documentação BaseIA Extract

Este é o portal da documentação. Escolha o percurso de acordo com o que você
pretende fazer.

## Usar o framework

A [documentação operacional](operational/README.md) é a entrada principal. Ela
ensina a executar o pipeline em três ambientes:

1. [Local](operational/local/README.md) — instalação, inventário, amostragem,
   extração, render e auditoria;
2. [Desenvolvimento catalogado](operational/cataloged-development/README.md) —
   PostgreSQL, catálogo, S3 e runs persistentes;
3. [Produção](operational/production/README.md) — promoção da estratégia,
   infraestrutura e serviços externos.

Comece pelo [Quick Start local](operational/local/quickstart.md).

O fluxo recomendado registra cada conjunto de documentos como uma coleção.
Os PDFs, inventários, amostras e artefatos permanecem ao lado da origem
informada; a worktree contém somente código e documentação. Consulte
[Comandos de coleção](operational/reference/commands.md#contexto-de-colecao).

## Desenvolver o framework

A [documentação técnica](technical/README.md) descreve a estrutura do
repositório, a arquitetura avançada, os contratos do catálogo, a persistência
MinerU, o modelo de contexto por coleção e as regras de desenvolvimento.

## Fonte de produto

O propósito e as restrições de produto estão preservados integralmente em
[SOUL.md](SOUL.md). Esse documento é um manifesto de produto, não um
tutorial operacional.

## Convenções de navegação

Cada página possui:

- navegação para os três ambientes operacionais e para a área técnica;
- links de etapa anterior e próxima;
- links contextuais para conceitos ou implementações relacionadas.

Os metadados YAML no início de cada Markdown fornecem IDs e classificação
estáveis para uma futura interface de navegação.
