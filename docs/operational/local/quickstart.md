---
id: operational.local.quickstart
title: Quick Start local
kind: tutorial
audience: user
mode: local
stage: end-to-end
status: current
nav_order: 110
---

# Quick Start local

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

Este tutorial registra uma coleção que já existe em disco, cria uma amostra,
extrai e renderiza essa seleção e, por fim, incorpora um PDF novo. Nenhum PDF é
copiado para o repositório.

## Resultado esperado

Supondo uma fonte em `D:/colecoes/artigos`, o estado fica junto dela:

```text
D:/colecoes/artigos/
├── baseia.collection.yaml
├── .baseia/
│   ├── inventory/
│   │   ├── inventory.csv
│   │   └── sample.csv
│   ├── audit/
│   ├── extraction/
│   └── pipeline/
├── documento.pdf
└── documento/
    ├── manifest.json
    ├── intermediate/mineru/
    └── canonical/
        ├── document_ir.json
        ├── structure.json
        ├── document.md
        └── render.json
```

O Markdown do MinerU é intermediário. O único Markdown canônico é
`canonical/document.md`, produzido pelo render.

## 1. Instale o projeto

No PowerShell 7, na raiz do repositório:

```powershell
uv sync
uv run poe --help
```

Você não precisa ativar a `.venv`; `uv run` usa o ambiente correto.

## 2. Registre o diretório

Use o assistente:

```powershell
uv run poe init "D:/colecoes/artigos"
```

A primeira pergunta permite escolher uma coleção existente ou digitar `0` para
criar uma nova. Em uma coleção nova, o assistente pergunta nome, modo, escopo
de recursos, topologia, etapa-alvo e serviços.

O equivalente não interativo para uma coleção local que pretende chegar ao
render é:

```powershell
uv run poe init "D:/colecoes/artigos" `
    --name "Artigos" `
    --mode local `
    --resource-scope personal `
    --topology services `
    --through render `
    --execute register `
    --api-url "http://127.0.0.1:8000"
```

`register` cria, inventaria e audita, mas não inicia a extração. A saída
principal é `D:/colecoes/artigos/.baseia/inventory/inventory.csv`.

## 3. Confira e selecione a coleção

```powershell
uv run poe collection ls
uv run poe collection show "Artigos"
uv run poe collection use "Artigos"
```

`use` define o contexto padrão. Você também pode informar
`--collection "Artigos"` explicitamente nos comandos seguintes.

## 4. Crie uma amostra

```powershell
uv run poe sample --collection "Artigos" --size 3 --seed 42
```

Entrada: documentos válidos do inventário.
Saída: `D:/colecoes/artigos/.baseia/inventory/sample.csv`.

A amostra contém referências; ela não copia nem move documentos.

## 5. Extraia e renderize a amostra

Uma URL MinerU pode apontar para um processo local, um container ou um serviço
externo. Containers não são obrigatórios:

```powershell
$MineruUrl = "http://127.0.0.1:8000"
Invoke-RestMethod "$MineruUrl/baseia-capabilities"

uv run poe pipeline `
    --collection "Artigos" `
    --through render `
    --sample `
    --api-url $MineruUrl `
    --workers 3
```

O pipeline executa, nessa ordem:

1. auditoria da seleção;
2. extração MinerU;
3. auditoria do intermediário;
4. render canônico;
5. auditoria do render.

`--sample` vale para `inventory`, `extract` e `render`. Ele não pode ser usado
com `promote`, pois uma seleção parcial não deve substituir o snapshot ativo da
coleção. Para promover esses três PDFs como conjunto autônomo, registre-os
como uma coleção própria.

## 6. Confira as saídas

```powershell
$State = "D:/colecoes/artigos/.baseia"

Get-Content -Raw "$State/audit/extraction/summary.json"
Get-Content -Raw "$State/pipeline/latest.json"
Get-ChildItem "D:/colecoes/artigos" -Recurse -Filter "document.md"
```

O resumo deve indicar zero falhas e a mesma contagem de páginas esperadas e
extraídas.

## 7. Incorpore rapidamente um novo PDF

Quando chegar um novo paper:

```powershell
uv run poe quick "D:/entrada/novo-paper.pdf" `
    --collection "Artigos" `
    --api-url $MineruUrl
```

O arquivo permanece em `D:/entrada`. O BaseIA adiciona essa fonte ao YAML da
coleção, atualiza o inventário e leva o documento até a etapa-alvo configurada,
que neste exemplo é `render`.

## Sobre `--workers 3`

Três é o default conservador. No inventário e render, o valor depende de CPU,
RAM e I/O locais. No extract, ele também depende da capacidade agregada dos
serviços MinerU. Os limites não representam automaticamente GPUs; consulte o
[TODO técnico de concorrência](../../technical/backlog/concurrency-model.md).

Anterior: [Execução local](README.md)
Próximo: [Instalação](installation.md)
Detalhes: [Comandos](../reference/commands.md)
Avançado: [Modelo do pipeline](../../technical/concepts/pipeline.md)
