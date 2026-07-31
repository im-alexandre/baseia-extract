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

O render transforma o `middle.json` físico do MinerU em IR validado, estrutura
documental, metadados bibliográficos e Markdown semântico canônico.

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

Entrada obrigatória por documento: exatamente um `*_middle.json` físico válido
em `intermediate/mineru/`. Quando existir `content_list_v2.json`, ele é
reconciliado com o IR para preservar evidências de ordem e papéis; se estiver
ausente ou divergir na contagem de páginas, o render continua com a ordem
física do `middle.json` e registra um aviso.

```text
arquivo/canonical/
├── document_ir.json
├── structure.json
├── metadata.json
├── document.md
└── render.json
```

| Artefato | Papel |
| --- | --- |
| `document_ir.json` | representação normalizada e validada |
| `structure.json` | estrutura documental inferida |
| `metadata.json` | metadados bibliográficos e marcações de revisão |
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

Para listar campos que ainda exigem validação humana sem modificar nada:

```powershell
uv run poe review --path "D:/colecoes/artigos"
```

O comando alerta a quantidade de `metadata.json` ausentes; use `--format json`
para integrar a saída a outra ferramenta.

## Confirmar autores manualmente

Quando a inferência não for suficiente, registre a decisão durável em
`<raiz>/.baseia/metadata-overrides.yaml`. A chave é o caminho relativo do PDF
dentro da coleção; o render não consulta nem promove o campo `/Author` nativo
do PDF.

```yaml
schema_version: 1
documents:
  "artigo.pdf":
    authors: ["Nome da Autora", "Nome do Autor"]
    source: first_page_author_block
  "norma.pdf":
    authors: []
    corporate_authors: ["Órgão responsável"]
    no_personal_author: true
    source: institutional_or_contract
    note: "Documento institucional sem autoria pessoal."
```

As origens aceitas são `first_page_author_block`,
`bibliographic_reference_or_synthetic_metadata_sheet` e
`institutional_or_contract`. O último caso exige
`no_personal_author: true`; autores pessoais e essa marca não podem coexistir.

Depois de salvar as decisões, regenere apenas o render e confira que a fila
ficou vazia:

```powershell
$Root = "D:/colecoes/artigos"

uv run poe render --path $Root --workers 3 --overwrite
uv run poe review --path $Root
```

Os autores confirmados recebem confiança `1.0`, proveniência manual e
sobrenome derivado do último token para a citação inicial. O hash da decisão
entra em `render.json`; mudar uma decisão invalida o render daquele documento
sem refazer a extração.

## Regerar no fluxo de baixo nível

`uv run poe render --workers 3 --overwrite` continua disponível para
manutenção direta do contexto legado. No fluxo de coleção, artefatos atuais
são reutilizados e o relatório indica `skipped`.

Anterior: [Primeira extração](extraction.md)
Próximo: [Auditoria e recuperação](audit-and-recovery.md)
Referência: [Artefatos e saídas](../reference/artifacts.md)
Avançado: [Contrato de artefatos](../../technical/concepts/artifacts.md)
