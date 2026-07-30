---
id: operational.local.inventory
title: Primeiro inventário
kind: tutorial
audience: user
mode: local
stage: inventory
status: current
nav_order: 130
---

# Primeiro inventário

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é e para que serve

O inventário registra a composição observada da coleção: identidade lógica,
path físico atual, SHA-256, tamanho, páginas, propriedades do PDF e validade.
Ele é a entrada de amostragem, extração, render, auditoria e promoção.

O inventário de uma coleção registrada é novo e não importa task IDs, tentativas,
pods, duração, URLs de backend nem histórico de runs.

## Criar a coleção e o inventário

```powershell
uv run poe init "D:/colecoes/artigos" `
    --name "Artigos" `
    --mode local `
    --resource-scope personal `
    --topology local `
    --through inventory `
    --execute register
```

Entrada: PDF ou diretório em disco.
Saídas:

```text
D:/colecoes/artigos/baseia.collection.yaml
D:/colecoes/artigos/.baseia/inventory/inventory.csv
D:/colecoes/artigos/.baseia/inventory/inventory_errors.csv
D:/colecoes/artigos/.baseia/audit/inventory/
```

Os documentos não são copiados.

## Atualizar depois de mudanças

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through inventory `
    --refresh `
    --workers 3
```

Use `--refresh` depois de adicionar, remover, renomear ou alterar PDFs. Sem ele,
o pipeline reutiliza o inventário persistido.

## Campos centrais

| Campo | Significado |
| --- | --- |
| `collection` / `collection_slug` | nome humano e identificador normalizado |
| `document_id` | identidade determinística de coleção + path relativo |
| `revision_id` | identidade da revisão observada |
| `sha256` | integridade integral do conteúdo |
| `collection_relative_path` | path lógico dentro da coleção |
| `path` | localização física local, não publicada como identidade |
| `artifact_dir` / `manifest_path` | diretório irmão e manifesto materializado |
| `page_count` | páginas lidas do PDF |
| `status` / `error` | validade operacional e causa de falha |

Caminhos diferentes são documentos diferentes, mesmo com o mesmo SHA-256. O
BaseIA não cria aliases.

## Verificar

```powershell
$Inventory = Import-Csv `
    "D:/colecoes/artigos/.baseia/inventory/inventory.csv"

$Inventory | Measure-Object
$Inventory | Group-Object status | Select-Object Name, Count
Get-Content -Raw `
    "D:/colecoes/artigos/.baseia/audit/inventory/summary.json"
```

O pipeline não avança para extração quando há documentos inválidos.

## Comando legado

`uv run poe inventory` continua disponível para o snapshot legado em
`data/documents`. Para novas coleções, prefira `poe init` e `poe pipeline`,
pois eles preservam configuração e estado junto à fonte.

Anterior: [Instalação](installation.md)
Próximo: [Primeira amostragem](sampling.md)
Referência: [Artefatos e saídas](../reference/artifacts.md)
Avançado: [Catálogo, inventário e identidade](../../technical/concepts/catalog.md)
