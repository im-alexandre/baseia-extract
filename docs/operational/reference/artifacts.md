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
│   ├── ingest/
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
        ├── metadata.json
        ├── document.md
        ├── render.json
        ├── chunks/<perfil>.jsonl
        └── ingest/<perfil>.json
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
| render | `*_middle.json` e `content_list_v2.json` opcional | IR, estrutura, metadados, Markdown e proveniência |
| ingest prepare | artefatos canônicos + política | `chunks/<perfil>.jsonl`, `ingest/<perfil>.json` e sumário local |
| ingest apply | chunks preparados + OpenRouter/Qdrant | pontos Qdrant reconciliados e sumário de conclusão |
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
| `canonical/metadata.json` | metadados bibliográficos e itens que exigem revisão |
| `canonical/document.md` | único Markdown canônico |
| `canonical/render.json` | canônico |
| `canonical/chunks/<perfil>.jsonl` | chunks estruturais da política |
| `canonical/ingest/<perfil>.json` | estado, hashes e resultado da ingestão por perfil |
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

Os chunks mantêm assets no payload: quando habilitado pela política, arquivos
de imagem são incluídos em `data_base64`. O texto enviado para embedding usa
placeholders e captions para figuras, tabelas e equações; referências podem
ser mantidas apenas no payload ou excluídas pela política.

Cada chunk também registra a object key determinística do PDF original. Quando
`BASEIA_S3_BUCKET` está configurado, o payload inclui a URI `s3://` calculada
antes do upload; ela só passa a representar um objeto disponível depois da
promoção.

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
