---
id: technical.concepts.pipeline
title: Modelo do pipeline
kind: concept
audience: maintainer
mode: all
stage: pipeline
status: current
nav_order: 550
---

# Modelo do pipeline

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md)

O pipeline transforma fontes físicas em artefatos canônicos e snapshots sem
usar diretórios temporários como contrato entre serviços.

## Ciclo de vida implementado

```mermaid
flowchart LR
    A["poe init"] --> B["Inventory"]
    B --> C["Inventory audit"]
    C --> D["Extract"]
    D --> E["Extract audit"]
    E --> F["Render"]
    F --> G["Render audit"]
    G --> H["Ingest"]
    H --> I["Promote S3/catalog"]
```

`collection_worker.py` executa os checkpoints em subprocesso com o contexto da
coleção. Uma falha de auditoria interrompe a sequência.

## Stages

| Stage | Entrada | Saída | Dono |
| --- | --- | --- | --- |
| `inventory` | fontes PDF | CSV, integridade e manifesto validado | collection/inventory |
| `extract` | revisão e URL MinerU | intermediários e referências S3 | MinerU + adapter |
| `render` | `middle.json` | IR, estrutura, Markdown e proveniência | render |
| `ingest` | artefatos canônicos + política YAML | chunks locais e, em `apply`, pontos Qdrant | ingest |
| `promote` | inventário integral e manifests | objetos verificados e snapshot ativo | bootstrap_s3/catalog |

`ingest` exige uma política declarada em `strategy.ingest_policy` no YAML da
coleção ou em `BASEIA_INGEST_POLICY`. `prepare` materializa e valida os chunks
locais; o pipeline usa `apply`, que também gera embeddings e reconcilia o
Qdrant. `promote` não pode anteceder essa etapa.

## Revisão de metadados

O render preserva candidatos bibliográficos, proveniência, confiança e flags
de revisão em `canonical/metadata.json`. `poe review --path <diretório>` é uma
leitura sem escrita: seleciona o inventário, lista apenas atributos com
`review.required=true` e informa `metadata.json` ausentes. A saída padrão é
tabela; `--format json` produz o mesmo resultado estruturado.

## Amostras

`poe sample` cria apenas uma seleção referencial. `pipeline --sample` usa esse
CSV em inventory, extract, render e auditorias, sem copiar PDFs.

Promoção de amostra é proibida. Um snapshot ativo representa a coleção
integral. Para transformar a seleção em autoridade independente, ela deve ser
registrada como outra coleção.

## `init`, `pipeline` e `quick`

- `init`: cria coleção ou adiciona uma fonte; sempre inventaria e audita;
- `pipeline`: retoma ou avança até um checkpoint;
- `quick`: adiciona uma fonte e executa até a etapa-alvo vigente;
- `collection use`: muda somente o contexto padrão.

Adicionar uma fonte a coleção existente calcula a etapa observada antes da
mudança e conduz os novos documentos até ela. O lock de arquivo evita dois
workers locais simultâneos para a mesma coleção; ele não substitui leases do
catálogo em topologias distribuídas.

## Idempotência

- documento: UUID determinístico de coleção + path;
- revisão: documento + SHA-256;
- task MinerU: revisão, configuração e inputs;
- snapshot: escopo + hash do inventário serializado;
- upload: object key + SHA-256 + tamanho.

Uma repetição reconcilia tasks persistidas, ignora render atual e reutiliza
snapshot idêntico. Mudança de composição produz snapshot novo e preserva o
anterior.

## Propriedade do Markdown

Extract produz intermediários. O render é o único produtor de
`canonical/document.md`. O Markdown MinerU nunca é promovido como Markdown
final.

## Boundary de produção

Produção recria YAML, inventário, manifests, snapshots e runs. Apenas a
estratégia é reaplicada. O handoff de autoridade para um snapshot bruto antes
de extract/render ainda está no
[backlog](../backlog/production-authority-handoff.md).

Anterior: [Persistência MinerU](../architecture/mineru-persistence.md)
Próximo: [Catálogo e identidade](catalog.md)
Operação relacionada: [Quick Start](../../operational/local/quickstart.md)
