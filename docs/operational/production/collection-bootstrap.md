---
id: operational.production.bootstrap
title: Registrar, executar e ativar a coleção
kind: tutorial
audience: operator
mode: production
stage: inventory
status: current
nav_order: 330
---

# Registrar, executar e ativar a coleção

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## 1. Registrar sem processar

```powershell
uv run poe init "E:/entregas/acme/documentos" `
    --name "Acme Produção" `
    --mode production `
    --resource-scope client `
    --topology distributed `
    --through promote `
    --execute register `
    --api-url "https://gpu-a.example" `
    --api-url "https://gpu-b.example"
```

O comando cria inventário e auditoria do zero. Os documentos e `.baseia`
permanecem em `E:/entregas/acme/documentos`.

## 2. Fazer um smoke por amostra

```powershell
uv run poe sample --collection "Acme Produção" --size 3
uv run poe pipeline `
    --collection "Acme Produção" `
    --through render `
    --sample
```

Inspecione o Markdown canônico e os relatórios. Uma amostra não é promovida.

## 3. Executar e promover o conjunto completo

```powershell
uv run poe pipeline `
    --collection "Acme Produção" `
    --through promote `
    --workers 3
```

O pipeline:

1. audita o inventário integral;
2. extrai documentos pendentes;
3. audita intermediários;
4. renderiza canônicos;
5. audita o render;
6. publica objetos e snapshot;
7. ativa o snapshot no escopo da coleção.

## Autoridade e limite atual

O snapshot ativo do S3/catálogo é a autoridade publicada. Paths absolutos e
histórico de desenvolvimento não entram nele.

Hoje, o comando integrado promove o snapshot depois de extract e render. O
handoff anterior ao processamento — subir apenas PDFs brutos, inventariar o
S3 e abandonar imediatamente o inventário local — ainda exige uma separação
explícita de snapshots e está no
[soft backlog de autoridade](../../technical/backlog/production-authority-handoff.md).

`poe bootstrap` não inicia coleções novas; ele mantém a consolidação legada.
`poe promote-s3` é a primitiva genérica de baixo nível usada pelo pipeline.

Anterior: [Ambiente com Compose](compose-environment.md)
Próximo: [Executar o pipeline](execute-pipeline.md)
Referência: [Artefatos e saídas](../reference/artifacts.md)
Avançado: [Inventário e snapshots](../../technical/concepts/catalog.md)
