---
id: operational.cataloged.rendering
title: Renderizar e publicar canônicos
kind: tutorial
audience: operator
mode: cataloged-development
stage: render
status: current
nav_order: 240
---

# Renderizar e publicar canônicos

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Dev catalogado](README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Renderizar sem promover

```powershell
uv run poe pipeline `
    --collection "Acme Diagnóstico" `
    --through render
```

O render materializa `document_ir.json`, `structure.json`, `metadata.json`,
`document.md` e `render.json` no diretório irmão de cada PDF e atualiza o manifesto. O
`document.md` do render é o Markdown canônico; o Markdown MinerU não é
publicado como final.

## Publicar e ativar

`promote` inclui `ingest`. Antes dele, o YAML da coleção deve conter
`strategy.ingest_policy`, e o processo precisa ter `OPENROUTER_API_KEY`. A
credencial Qdrant indicada pela política só é necessária quando o endpoint
exigir autenticação.

```powershell
uv run poe pipeline `
    --collection "Acme Diagnóstico" `
    --through promote
```

Entradas: inventário integral válido e manifests v2.
Saídas:

- objetos sob `<collection-slug>/<path>/...`;
- chunks, sumário de ingestão e pontos Qdrant reconciliados;
- inventário JSONL e manifesto do snapshot;
- snapshot ativo no catálogo;
- `.baseia/bootstrap/s3/<scope>/<snapshot-id>/promotion-report.json`;
- `.baseia/pipeline/latest.json`.

O manifesto do documento é publicado depois dos payloads. A promoção compara
SHA-256 e tamanho, não ETag.

## Amostras

`--sample` pode chegar até `render`, mas é rejeitado em `promote`. A coleção
catalogada é definida por um inventário completo, não por uma seleção
diagnóstica.

Anterior: [Extrair com persistência](extraction.md)
Próximo: [Preparar a estratégia](promotion.md)
Referência: [Artefatos e saídas](../reference/artifacts.md)
Avançado: [Contrato de artefatos](../../technical/concepts/artifacts.md)
