---
id: operational.local.audit-recovery
title: Auditoria e recuperação
kind: tutorial
audience: user
mode: local
stage: audit
status: current
nav_order: 170
---

# Auditoria e recuperação

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Auditorias automáticas

`poe pipeline` cria checkpoints e só avança quando a etapa anterior é válida:

| Depois de | O que é verificado |
| --- | --- |
| inventory | paths, identidades, validade e páginas |
| extract | presença e validade do `middle.json`, páginas e schema observado |
| render | IR, estrutura, Markdown canônico, manifesto e órfãos |
| promote | checksums S3, contagens e ativação do snapshot |

Os relatórios ficam em `<raiz>/.baseia/audit/`. O relatório completo da última
execução fica em `<raiz>/.baseia/pipeline/latest.json`.

## Executar somente a auditoria necessária

```powershell
uv run poe pipeline --collection "Artigos" --through inventory
uv run poe pipeline --collection "Artigos" --through extract --sample
uv run poe pipeline --collection "Artigos" --through render --sample
```

Cada comando pode retomar trabalho pendente. Para apenas inspecionar o layout
legado, `uv run poe audit` continua disponível.

## Interpretar status

- `PASS`: contrato cumprido;
- `WARN`: artefato válido com observação para revisão;
- `FAIL`: etapa incompleta ou inconsistente; o pipeline para.

Um `WARN` de `unknown_block_types=index` significa que o MinerU classificou
blocos de índice, sumário ou remissivo fora da taxonomia semântica conhecida.
O conteúdo permanece no IR como `OTHER`; ele não indica perda de páginas nem
corrompe o documento. O refinamento dessa taxonomia está registrado no
[soft backlog](../../technical/backlog/semantic-block-types.md).

## Recuperar extração remota

```powershell
uv run poe recover-extract "https://mineru.example"
uv run poe recover-extract "https://mineru.example" --apply
```

O primeiro comando planeja. `--apply` materializa resultados já persistidos no
result store, sem reenviar o PDF.

## Reexecutar

O pipeline é idempotente:

```powershell
uv run poe pipeline --collection "Artigos" --through render
```

Artefatos atuais são reutilizados. Uma promoção repetida do mesmo inventário
verifica os objetos e reutiliza o snapshot ativo; uma composição alterada gera
um novo snapshot e torna o anterior histórico.

Anterior: [Primeiro render](rendering.md)
Próximo: [Desenvolvimento catalogado](../cataloged-development/README.md)
Referência: [Comandos](../reference/commands.md)
Avançado: [Transações e idempotência](../../technical/architecture/catalog.md)
