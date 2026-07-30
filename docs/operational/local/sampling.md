---
id: operational.local.sampling
title: Primeira amostragem
kind: tutorial
audience: user
mode: local
stage: sampling
status: current
nav_order: 140
---

# Primeira amostragem

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é

A amostragem seleciona referências para um subconjunto reproduzível dos
documentos válidos. Ela permite avaliar parsing e render antes de processar
toda a coleção.

## Criar

```powershell
uv run poe sample `
    --collection "Artigos" `
    --size 10 `
    --seed 42
```

Entrada: `.baseia/inventory/inventory.csv` da coleção.
Saída: `.baseia/inventory/sample.csv` na mesma raiz.

`--size` limita a quantidade e `--seed` torna a seleção reproduzível para o
mesmo inventário. Nenhum PDF é copiado ou movido.

## Inspecionar

```powershell
$Sample = Import-Csv `
    "D:/colecoes/artigos/.baseia/inventory/sample.csv"

$Sample | Measure-Object
$Sample |
    Select-Object collection_relative_path, page_count, sha256
```

## Executar a seleção

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through render `
    --sample `
    --api-url "http://127.0.0.1:8000"
```

O pipeline valida a amostra contra o inventário atual e rejeita identidades,
revisões ou hashes obsoletos. Gere novamente a amostra depois de mudanças no
inventário.

Uma amostra pode chegar até `render`, mas não até `promote`. Promoção define a
composição canônica da coleção inteira. Caso a seleção deva ser promovida como
um conjunto independente, registre-a como uma nova coleção.

Anterior: [Primeiro inventário](inventory.md)
Próximo: [Primeira extração](extraction.md)
Referência: [Comandos](../reference/commands.md)
Avançado: [Modelo de identidade](../../technical/concepts/catalog.md)
