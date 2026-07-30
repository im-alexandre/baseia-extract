---
id: technical.backlog.generic-bootstrap
title: "CAT-001 concluído: promoção genérica de coleções"
kind: decision-record
audience: maintainer
mode: production
stage: inventory
status: completed
nav_order: 592
---

# CAT-001 concluído: promoção genérica de coleções

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Resultado implementado

- `poe init` registra qualquer PDF ou diretório sem copiar a fonte;
- `baseia.collection.yaml` descreve múltiplas fontes e serviços;
- `poe pipeline` executa checkpoints por coleção;
- `promote-s3` aceita inventário, filtros e escopo arbitrários;
- IDs de snapshot dependem do escopo e hash do inventário;
- uploads são checksum-aware e retomáveis;
- a Catalog API reutiliza snapshots idênticos e substitui o ativo do mesmo
  escopo quando a composição muda;
- relatórios ficam junto à coleção.

`bootstrap.py` continua propositalmente legado. Sua especificidade não limita
`bootstrap_s3.py`.

## Validação

O fluxo foi validado com uma coleção autônoma de três PDFs e com adição direta
de um PDF a uma coleção já promovida. Repetir `promote` reutilizou o snapshot
ativo sem duplicar o estado lógico.

## Necessidades separadas

O handoff de autoridade antes do processamento está em
[CAT-002](production-authority-handoff.md). Workspaces multi-coleção estão em
[CTX-001](workspace-contexts.md).

Anterior: [CAP-001 — Concorrência](concurrency-model.md)
Próximo: [CTX-001 — Workspaces](workspace-contexts.md)
Operação relacionada: [Registrar e ativar](../../operational/production/collection-bootstrap.md)
