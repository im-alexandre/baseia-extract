---
id: operational.cataloged.inventory
title: Inventariar e promover no ambiente catalogado
kind: tutorial
audience: operator
mode: cataloged-development
stage: inventory
status: current
nav_order: 220
---

# Inventariar e promover no ambiente catalogado

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Dev catalogado](README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Registrar a coleção

```powershell
uv run poe init "D:/clientes/acme/documentos" `
    --name "Acme Diagnóstico" `
    --mode cataloged `
    --resource-scope operator `
    --topology services `
    --through promote `
    --execute register `
    --api-url "http://127.0.0.1:8000"
```

`register` cria o YAML, inventaria e audita sem disparar a coleção inteira. O
inventário fica em `D:/clientes/acme/documentos/.baseia/inventory/`.

## Validar uma amostra

```powershell
uv run poe sample --collection "Acme Diagnóstico" --size 10
uv run poe pipeline `
    --collection "Acme Diagnóstico" `
    --through render `
    --sample
```

## Promover a coleção completa

```powershell
uv run poe pipeline `
    --collection "Acme Diagnóstico" `
    --through promote `
    --workers 3
```

O pipeline audita inventário, extrai pendências, renderiza, audita novamente,
publica todos os artefatos por SHA-256, registra o snapshot e o ativa no escopo
`acme-diagnostico`.

Uma reexecução idêntica verifica objetos e reutiliza o snapshot ativo. Se a
composição mudar, o inventário gera outro ID de snapshot; ao ativá-lo, o
anterior vira histórico.

## Planejamento de baixo nível

Para inspecionar o contrato sem executar as demais etapas:

```powershell
uv run poe promote-s3 plan `
    --inventory "D:/clientes/acme/documentos/.baseia/inventory/inventory.csv" `
    --scope "acme-diagnostico"
```

`promote-s3` é genérico. `plan` apenas gera o snapshot local; `apply` publica.
No uso normal, prefira `poe pipeline --through promote`, que inclui as
auditorias obrigatórias.

Anterior: [Preparar o ambiente](environment.md)
Próximo: [Extrair com persistência](extraction.md)
Referência: [Comandos](../reference/commands.md)
Avançado: [Catálogo e identidade](../../technical/concepts/catalog.md)
