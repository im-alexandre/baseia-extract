---
id: operational.reference.commands
title: Referência de comandos
kind: reference
audience: operator
mode: all
stage: commands
status: current
nav_order: 410
---

# Referência de comandos

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](README.md) ·
[Documentação técnica](../../technical/README.md)

Use `uv run poe`; a `.venv` não precisa estar ativada. A ajuda é a fonte
executável de defaults e escolhas:

```powershell
uv run poe --help
uv run poe --help collection
uv run poe --help pipeline
```

## Contexto de coleção

```powershell
uv run poe collection ls
uv run poe collection current
uv run poe collection show "NOME"
uv run poe collection use "NOME"
uv run poe collection "NOME"
uv run poe collection configure "NOME" [opções]
```

| Ação | Para que serve | Quando usar |
| --- | --- | --- |
| `ls` | lista coleções, contagem e etapa observada | descobrir contextos |
| `current` | mostra o contexto atual e seu YAML | conferir antes de operar |
| `show NOME` | mostra uma coleção sem selecioná-la | diagnosticar configuração |
| `use NOME` | define a coleção padrão | alternar entre trabalhos |
| `configure NOME` | altera modo, escopo, topologia, etapa ou serviços | preparar outro ambiente |

`configure` preserva campos com `keep`. Para URLs opcionais, `-` remove o
valor. `--api-url` pode ser repetido e substitui a lista MinerU persistida.
Credenciais são informadas por nomes de variáveis, nunca por valores.

## Inicializar ou adicionar uma fonte

```powershell
uv run poe init PATH
```

Sem `--collection` ou `--name`, abre o assistente. A primeira pergunta mostra
as coleções disponíveis; `0` cria uma nova.

Principais opções:

| Opção | Default | Escolhas e efeito |
| --- | --- | --- |
| `--collection` | vazio | adiciona o path a uma coleção existente |
| `--name` | vazio | cria uma coleção nova sem perguntas |
| `--mode` | `ask` | `local`, `cataloged`, `production` |
| `--resource-scope` | `ask` | `personal`, `operator`, `client` |
| `--topology` | `ask` | `local`, `services`, `distributed` |
| `--through` | `auto` | etapa-alvo: `inventory`, `extract`, `render`, `ingest`, `promote`; `ingest` aplica a política vetorial e antecede `promote` |
| `--execute` | `auto` | `register` inventaria; `run` executa; `auto` executa adições a coleção existente e apenas registra uma nova |
| `--prefix` | raiz lógica | coloca a fonte em um subdiretório lógico |
| `--api-url` | configuração/ambiente | endpoint MinerU; repetível |
| `--workers` | `3` | paralelismo local/capacidade inicial |
| `--recursive` | `true` | inclui subdiretórios |

Os PDFs ficam na origem. Coleções novas recebem
`baseia.collection.yaml` e `.baseia/` junto à fonte.

## Inventariar, amostrar e executar

```powershell
uv run poe sample --collection "NOME" --size 100 --seed 42

uv run poe pipeline `
    --collection "NOME" `
    --through auto `
    --workers 3
```

| Opção de `pipeline` | Default | Efeito |
| --- | --- | --- |
| `--collection` | coleção atual | escolhe explicitamente |
| `--through` | `auto` | usa a etapa-alvo ou encerra no checkpoint escolhido |
| `--api-url` | YAML/ambiente | sobrescreve endpoints só nesta execução |
| `--workers` | `3` | capacidade da execução |
| `--refresh` | `false` | relê todas as fontes antes de executar |
| `--sample` | `false` | executa seleção até `render`; é incompatível com `promote` |

Ordem implementada:

```text
inventory → extract → render → ingest → promote
```

Cada seta inclui uma auditoria. `ingest` prepara chunks, gera embeddings via
OpenRouter e reconcilia os pontos no Qdrant; `promote` exige que a política de
ingestão esteja configurada.

## Adição rápida

```powershell
uv run poe quick "D:/entrada/paper.pdf" `
    --collection "Minha Dissertação"
```

`quick` registra o PDF ou diretório, atualiza o inventário e executa até a
etapa-alvo da coleção. Use `--through` para limitar aquela execução,
`--prefix` para o path lógico e `--api-url` para sobrescrever o MinerU.

## Tasks de baixo nível

Estas tasks operam o contexto definido por variáveis e são úteis para
manutenção, diagnóstico e compatibilidade legada:

```powershell
uv run poe inventory --workers 3
uv run poe extract start URL... --workers 3 --sample
uv run poe extract status
uv run poe extract watch
uv run poe extract stop
uv run poe recover-extract URL...
uv run poe recover-extract URL... --apply
uv run poe render --workers 3 --overwrite
uv run poe review --path "D:/colecoes/artigos"
uv run poe review --path "D:/colecoes/artigos" --format json
uv run poe ingest prepare --policy "D:/politicas/embedding.yaml"
uv run poe ingest apply --path "D:/colecoes/artigos"
uv run poe audit
```

No uso normal de coleções registradas, prefira `pipeline`; ele injeta paths e
serviços da coleção no worker isolado.

### Revisões de metadados

`review` é somente leitura: seleciona o inventário existente e lista as
revisões requeridas em `canonical/metadata.json`, sem reextrair, renderizar ou
alterar artefatos. `--format table` é o default; `--format json` inclui o
inventário, a quantidade selecionada, o alerta `missing_metadata` e os itens.
Cada item tem `path`, `relative_path`, `document_id`, `attribute`, `candidate`,
`status`, `reason` e `provenance`.

### Ingestão vetorial

```powershell
uv run poe ingest prepare `
    --path "D:/colecoes/artigos"

uv run poe ingest apply `
    --path "D:/colecoes/artigos" `
    --qdrant-url "http://127.0.0.1:6333"
```

`prepare` usa somente os artefatos canônicos locais e grava chunks e sumários.
`apply` também exige a credencial OpenRouter e envia embeddings, criando ou
validando a coleção Qdrant e reconciliando pontos idempotentemente. `--path`
seleciona documentos do inventário vigente sob aquele diretório; não recria o
inventário nem reexecuta a extração.

A política é resolvida nesta ordem: `--policy`; `strategy.ingest_policy` no
`baseia.collection.yaml` sob `--path`; `<raiz>/.baseia/embedding.yaml`; e
`BASEIA_INGEST_POLICY`. Para a task direta sem um YAML de coleção, a descoberta
sob `--path` usa a política convencional antes do fallback global.

## Bootstrap legado

```powershell
uv run poe bootstrap plan --workers 3
uv run poe bootstrap apply --workers 3
uv run poe bootstrap refresh-manifests --workers 3
```

| Ação | O que faz |
| --- | --- |
| `plan` | inspeciona a consolidação legada e grava um plano, sem aplicá-lo |
| `apply` | aplica o plano validado, incluindo layout e quarentena |
| `refresh-manifests` | reescreve manifests do inventário legado já consolidado, preservando dados compatíveis |

`bootstrap` não é o inicializador de coleções novas.

## Promoção S3 de baixo nível

```powershell
uv run poe promote-s3
uv run poe promote-s3 plan
uv run poe promote-s3 apply `
    --inventory "D:/colecao/.baseia/inventory/inventory.csv" `
    --scope "minha-colecao"
```

Sem ação, o default é `plan`. A diferença:

- `plan`: valida o inventário e gera JSONL/manifesto do snapshot localmente;
- `apply`: também verifica/envia objetos, importa documentos e ativa o
  snapshot no catálogo.

`--collection` filtra uma ou mais coleções de um CSV; `--scope` é obrigatório
quando a seleção reúne mais de uma. Lotes usam `--batch-size 100` e
`--upload-batch-size 2000`.

## Catálogo e documentação

```powershell
uv run poe catalog-migrate
uv run poe catalog-api
uv run poe docs-build
uv run poe docs-serve
```

Anterior: [Referência operacional](README.md)
Próximo: [Configuração](configuration.md)
Tutorial: [Quick Start](../local/quickstart.md)
Avançado: [Entry points](../../technical/repository-structure.md#entry-points-e-tasks)
