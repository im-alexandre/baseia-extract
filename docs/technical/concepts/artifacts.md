---
id: technical.concepts.artifacts
title: Artefatos e layout
kind: concept
audience: maintainer
mode: all
stage: artifacts
status: current
nav_order: 570
---

# Artefatos e layout

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md)

## Layout em disco

```text
<raiz-da-coleção>/
├── baseia.collection.yaml
├── .baseia/
├── <path>/documento.pdf
└── <path>/documento/
    ├── manifest.json
    ├── intermediate/
    │   └── mineru/**
    └── canonical/
        ├── document_ir.json
        ├── structure.json
        ├── metadata.json
        ├── document.md
        ├── render.json
        ├── chunks/<política>.jsonl
        └── ingest/<política>.json
```

O arquivo original permanece diretamente navegável no diretório da coleção. O
diretório irmão agrupa todos os derivados sem alterar o nome do PDF.

## Layout S3

```text
<collection-slug>/<path>/documento.pdf
<collection-slug>/<path>/documento/manifest.json
<collection-slug>/<path>/documento/intermediate/mineru/**
<collection-slug>/<path>/documento/canonical/**

inventory/scopes/<scope>/snapshots/<snapshot-id>/
├── inventory.jsonl
└── manifest.json
```

Paths absolutos locais nunca são publicados.

## Manifest v2

O manifesto contém:

- schema e versão;
- identidade do documento e da revisão;
- SHA-256 e tamanho;
- content type;
- origem e stage run;
- object key de cada artifact;
- contagem e bytes do conjunto.

Ele é um índice materializado por documento, útil para inspeção e transporte.
O catálogo e o snapshot ativo continuam sendo os registros centralizados.

## Commit protocol

1. publicar objetos;
2. confirmar SHA-256 e tamanho;
3. registrar artifacts e conclusão no catálogo;
4. publicar o manifesto por último.

ETag não é usado como MD5, porque multipart e implementações S3 compatíveis
possuem semânticas diferentes.

## Canonicidade

`intermediate/mineru/*.md` pertence ao pacote intermediário. O render não o
mantém como representação final, não o usa como autoridade semântica e não o
copia para `canonical/`. `canonical/document.md` é sempre produzido pelo
render e é o único Markdown canônico.

No modo local, render escreve em disco. `pipeline --through promote` publica o
manifesto integral; a publicação direta do stage render continua opt-in por
`BASEIA_RENDER_PUBLISH_S3=true`.

## Projeções irmãs

`canonical/document_ir.json` é a representação física normalizada do
`middle.json`: conserva sem reescrita semântica os blocos modelados, spans,
geometria e blocos descartados. O `middle.json` continua sendo a evidência
completa do MinerU; `preproc_blocks` não é serializado no IR.
`content_list_v2`, quando presente nos intermediários MinerU, é reconciliado
um-a-um com os blocos do IR por página; ele propõe tipo e ordem de leitura, mas
não duplica texto nem substitui a evidência física.

`structure.json` é a `DocumentStructure` derivada dessa reconciliação.
`metadata.json` registra bibliografia, proveniência, confiança e revisão.
`document.md` é uma projeção de leitura e os chunks são uma projeção de
retrieval. Nenhuma dessas projeções é autoridade sobre as demais nem altera o
IR. O `render.json` fixa hashes, fonte do `content_list_v2`, avisos e status.

Uma decisão humana pode ser persistida fora dos canônicos em
`.baseia/metadata-overrides.yaml`, indexada pelo caminho relativo do PDF. O
render aplica essa decisão antes de gravar `metadata.json`, preserva autoria
corporativa separadamente e registra o hash específico da decisão em
`render.json`. Assim, a confirmação sobrevive a novos renders sem alterar o
IR nem recorrer aos metadados nativos do PDF.

Imagens permanecem nos intermediários e são referenciadas relativamente pelo
Markdown. Para retrieval, a política pode levar assets para o payload com hash,
MIME, HTML/LaTeX, caminho relativo e base64; ausências ficam explícitas. O
render preserva equações inline/interline como LaTeX e tenta converter tabelas
para Markdown a partir do PDF quando necessário.

Veja também: [Ingestão e retrieval](ingestion.md).

Anterior: [Catálogo e identidade](catalog.md)
Próximo: [Ingestão e retrieval](ingestion.md)
Operação relacionada: [Artefatos e saídas](../../operational/reference/artifacts.md)
