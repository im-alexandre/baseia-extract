---
id: operational.local.rendering
title: Primeiro render
kind: tutorial
audience: user
mode: local
stage: render
status: current
nav_order: 160
---

# Primeiro render

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é

O render transforma o `middle.json` MinerU em IR validado, estrutura
documental e Markdown semântico canônico.

## Executar depois da extração

Para a amostra vigente:

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through render `
    --sample
```

Para toda a coleção:

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through render
```

O pipeline retoma as etapas anteriores idempotentemente. Se a extração ainda
estiver pendente, ele precisa das URLs MinerU persistidas no YAML ou passadas
por `--api-url`.

## Entrada e saídas

Entrada por documento: exatamente um `*_middle.json` válido em
`intermediate/mineru/`.

```text
arquivo/canonical/
├── document_ir.json
├── structure.json
├── document.md
└── render.json
```

| Artefato | Papel |
| --- | --- |
| `document_ir.json` | representação normalizada e validada |
| `structure.json` | estrutura documental inferida |
| `document.md` | único Markdown canônico |
| `render.json` | proveniência e validações do render |

O render não publica o Markdown MinerU como final. Esse arquivo permanece
somente em `intermediate/mineru/` enquanto fizer parte do manifesto
intermediário.

## Verificar

```powershell
$Root = "D:/colecoes/artigos"

Get-Content -Raw "$Root/.baseia/render_summary.json"
Get-Content -Raw "$Root/.baseia/audit/extraction/summary.json"
Get-ChildItem $Root -Recurse -Filter "document.md"
```

Uma execução integral válida deve ter zero `failed`, contagem de páginas sem
diferença e um `document.md` por documento selecionado.

## Regerar no fluxo de baixo nível

`uv run poe render --workers 3 --overwrite` continua disponível para
manutenção direta do contexto legado. No fluxo de coleção, artefatos atuais
são reutilizados e o relatório indica `skipped`.

Anterior: [Primeira extração](extraction.md)
Próximo: [Auditoria e recuperação](audit-and-recovery.md)
Referência: [Artefatos e saídas](../reference/artifacts.md)
Avançado: [Contrato de artefatos](../../technical/concepts/artifacts.md)
