---
id: operational.production.operations
title: Operação e recuperação
kind: how-to
audience: operator
mode: production
stage: operations
status: current
nav_order: 360
---

# Operação e recuperação

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Verificações de rotina

```powershell
uv run poe collection ls
uv run poe collection show "Acme Produção"
docker compose --profile production ps
Invoke-RestMethod "$env:BASEIA_CATALOG_API_URL/health"
```

Para cada MinerU:

```powershell
Invoke-RestMethod "https://mineru.example/baseia-capabilities"
Invoke-RestMethod "https://mineru.example/baseia-persistence-health"
```

Não aumente a carga enquanto o serviço sinalizar backpressure por S3, backlog,
catálogo ou disco.

## Resposta perdida

```powershell
uv run poe recover-extract "https://mineru.example"
uv run poe recover-extract "https://mineru.example" --apply
```

Planeje primeiro. A recuperação consulta tarefas persistidas e não reenvia o
PDF.

## Reexecução e atualização

```powershell
uv run poe pipeline --collection "Acme Produção" --through promote
uv run poe pipeline --collection "Acme Produção" --through promote --refresh
```

Use `--refresh` somente quando a fonte mudou. O mesmo snapshot é reutilizado;
um inventário diferente produz nova revisão de snapshot e preserva o anterior.

## Capacidade

O default é três workers. Inventário/render dependem do host; extract depende
também da capacidade dos endpoints MinerU. Pools HTTP, downloads S3,
persistência no servidor e GPUs são limites distintos, conforme o
[TODO de concorrência](../../technical/backlog/concurrency-model.md).

## Backups

Proteja separadamente:

- diretório da coleção e `baseia.collection.yaml`;
- PostgreSQL;
- buckets canônico e de resultados;
- imagens fixadas;
- configuração sem valores de segredo.

Temporal não substitui esses procedimentos porque o pipeline ainda não possui
workflows ativos.

Anterior: [Usar serviços externos](external-services.md)
Próximo: [Referência operacional](../reference/README.md)
Avançado: [Transações e concorrência](../../technical/architecture/catalog.md)
