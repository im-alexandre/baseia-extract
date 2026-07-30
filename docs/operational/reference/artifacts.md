---
id: operational.reference.artifacts
title: Artefatos e saídas
kind: reference
audience: user
mode: all
stage: artifacts
status: current
nav_order: 430
---

# Artefatos e saídas

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](README.md) ·
[Documentação técnica](../../technical/README.md)

## Estado junto à coleção

```text
<raiz>/
├── baseia.collection.yaml
├── .baseia/
│   ├── inventory/
│   │   ├── inventory.csv
│   │   ├── inventory_errors.csv
│   │   └── sample.csv
│   ├── audit/
│   ├── extraction/
│   ├── bootstrap/s3/
│   ├── pipeline/
│   │   ├── latest.json
│   │   └── runs/
│   └── render_summary.json
├── caminho/documento.pdf
└── caminho/documento/
    ├── manifest.json
    ├── intermediate/mineru/
    └── canonical/
        ├── document_ir.json
        ├── structure.json
        ├── document.md
        └── render.json
```

O registro global contém apenas coleção atual e paths para os YAMLs. Por
default, ele usa o diretório de dados do usuário calculado por `platformdirs`;
`BASEIA_COLLECTIONS_DIR` permite sobrescrever.

## Saídas por etapa

| Etapa | Entrada | Saída |
| --- | --- | --- |
| init/inventory | PDF ou diretório | YAML, inventário e auditoria |
| sample | inventário válido | `sample.csv`, sem copiar PDFs |
| extract | inventário ou amostra | intermediários, manifests e runs |
| render | `*_middle.json` | IR, estrutura, Markdown e proveniência |
| audit | seleção e artefatos | summaries, failures, warnings e review sample |
| promote | inventário integral + manifests | objetos S3, snapshot e relatório |

## Canônico e intermediário

| Artefato | Classificação |
| --- | --- |
| PDF no path da fonte | entrada canônica |
| `intermediate/mineru/**` | intermediário e diagnóstico |
| Markdown MinerU | intermediário; não é publicado como final |
| `canonical/document_ir.json` | canônico |
| `canonical/structure.json` | canônico |
| `canonical/document.md` | único Markdown canônico |
| `canonical/render.json` | canônico |
| `manifest.json` | índice materializado e commit marker |

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

Payloads são enviados e verificados antes do manifesto. Integridade usa
SHA-256 e tamanho; ETag não é tratado como MD5.

## Reconciliação direta após a promoção

Não é necessário repetir a auditoria para demonstrar que a promoção preservou
o conjunto já validado. Compare:

1. `.baseia/inventory/inventory.csv`, pela identidade, revisão, SHA-256,
   tamanho e `collection_relative_path`;
2. o `manifest.json` irmão de cada documento, pela lista de artefatos,
   classificação, tamanho e SHA-256;
3. `.baseia/bootstrap/s3/<scope>/<snapshot-id>/inventory.jsonl`, que registra
   os mesmos documentos e artefatos com suas object keys;
4. o `manifest.json` e o `promotion-report.json` do snapshot, cujo
   `inventory_sha256` autentica o JSONL e cujas contagens registram os objetos
   verificados.

As diferenças de schema são intencionais: paths absolutos e metadados locais
de diagnóstico não fazem parte do snapshot; `collection_relative_path` vira
`relative_path`; `sha256`/`bytes` do manifesto local viram
`checksum_sha256`/`size_bytes`; e o snapshot inclui o próprio
`document_manifest` como artefato final. A reconciliação compara valores
normalizados, não igualdade textual entre os arquivos.

Esse procedimento prova preservação de identidade, PDF e bytes declarados.
Ele não substitui uma nova análise semântica dos documentos; essa análise já
deve ter sido concluída antes da promoção.

Anterior: [Configuração](configuration.md)
Próximo: [Documentação técnica](../../technical/README.md)
Tutorial: [Primeiro render](../local/rendering.md)
Avançado: [Contrato técnico de artefatos](../../technical/concepts/artifacts.md)
