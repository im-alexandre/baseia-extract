---
id: operational.cataloged.environment
title: Preparar o ambiente catalogado
kind: tutorial
audience: operator
mode: cataloged-development
stage: installation
status: current
nav_order: 210
---

# Preparar o ambiente catalogado

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Dev catalogado](README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Subir catálogo e S3 de referência

```powershell
uv sync
docker compose --profile catalog up -d --build
docker compose --profile catalog ps
```

Serviços do perfil:

| Serviço | Endpoint no host | Papel |
| --- | --- | --- |
| PostgreSQL | `127.0.0.1:5432` | metadados e snapshots |
| Catalog API | `http://127.0.0.1:8088` | único writer do catálogo |
| SeaweedFS S3 | `http://127.0.0.1:8333` | payload canônico |

Verifique:

```powershell
Invoke-RestMethod "http://127.0.0.1:8088/health"
Invoke-RestMethod "http://127.0.0.1:9333/cluster/status"
```

A Catalog API aplica as migrations Alembic ao iniciar.

## MinerU é opcional neste passo

Para executar o container GPU local:

```powershell
docker compose --profile catalog --profile gpu up -d --build
Invoke-RestMethod "http://127.0.0.1:8000/baseia-capabilities"
```

Também é válido usar um MinerU já executado no host ou uma ou mais URLs
externas. O catálogo não exige que a GPU esteja no mesmo Compose.

## Configurar credenciais

Copie `.env.example` apenas se ainda não houver `.env`:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Defaults locais não são adequados para redes compartilhadas ou produção.
Credenciais reais permanecem em variáveis de ambiente ou secret stores.

## Parar sem apagar dados

```powershell
docker compose --profile catalog down
```

Não acrescente `--volumes` sem intenção explícita de apagar PostgreSQL e S3.

Anterior: [Desenvolvimento catalogado](README.md)
Próximo: [Inventariar e promover](inventory.md)
Referência: [Configuração](../reference/configuration.md)
Avançado: [Visão geral da arquitetura](../../technical/architecture/overview.md)
