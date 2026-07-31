---
id: operational.production.external-services
title: Usar serviços externos
kind: how-to
audience: operator
mode: production
stage: deployment
status: current
nav_order: 350
---

# Usar serviços externos

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

O Compose é uma topologia de referência. A coleção persiste as URLs e os nomes
das variáveis de credencial; os valores dos segredos ficam no ambiente.

## Catálogo e S3 canônico externos

```powershell
$env:CLIENT_S3_ACCESS_KEY = "<access-key>"
$env:CLIENT_S3_SECRET_KEY = "<secret-key>"
$env:CLIENT_CATALOG_TOKEN = "<token>"

uv run poe collection configure "Acme Produção" `
    --catalog-api-url "https://catalog.example" `
    --s3-endpoint-url "https://s3.example" `
    --s3-bucket "baseia-production" `
    --s3-access-key-env "CLIENT_S3_ACCESS_KEY" `
    --s3-secret-key-env "CLIENT_S3_SECRET_KEY"
```

O token do catálogo usa `services.catalog_token_env` no YAML; altere esse
campo artesanalmente se o nome não for `BASEIA_CATALOG_API_TOKEN`.

## MinerU externo

```powershell
uv run poe collection configure "Acme Produção" `
    --api-url "https://mineru-a.example" `
    --api-url "https://mineru-b.example"
```

Cada servidor pode executar seu próprio `mineru-router` para agregar as GPUs
locais. O cliente distribui entre URLs; um router central adicional não é
necessário.

O container usa `MINERU_ROUTER_LOCAL_GPUS=auto`. O MinerU 3.4.4 detecta as
GPUs visíveis e inicia um worker por dispositivo; em um host com uma GPU, o
mesmo entrypoint inicia somente `local-gpu-0`. Para restringir dispositivos,
informe uma lista como `MINERU_ROUTER_LOCAL_GPUS=0,2`. A opção
`--gpus all` não pertence ao CLI dessa versão.

## Result store MinerU separado

Se o servidor GPU publica em outro MinIO/S3:

```powershell
$env:GPU_RESULTS_ACCESS_KEY = "<access-key>"
$env:GPU_RESULTS_SECRET_KEY = "<secret-key>"

uv run poe collection configure "Acme Produção" `
    --mineru-result-s3-endpoint-url "https://gpu-results.example" `
    --mineru-result-s3-bucket "mineru-results" `
    --mineru-result-s3-access-key-env "GPU_RESULTS_ACCESS_KEY" `
    --mineru-result-s3-secret-key-env "GPU_RESULTS_SECRET_KEY"
```

O endpoint é o endereço visto pelo cliente que materializa o `middle.json`.
Dentro do container GPU, `MINERU_S3_ENDPOINT_URL` pode usar outro hostname.

## PostgreSQL externo

Somente a Catalog API acessa diretamente o PostgreSQL. Configure
`BASEIA_DATABASE_URL` no deployment da API; clientes e MinerU usam HTTP.

## Qdrant

O Qdrant recebe os pontos da etapa `ingest`; ele pode estar no Compose ou ser
externo. Para um endpoint externo, declare `services.qdrant_url` e
`services.qdrant_api_key_env` no `baseia.collection.yaml` e mantenha o valor
da credencial no ambiente:

```yaml
services:
  qdrant_url: https://qdrant.example
  qdrant_api_key_env: CLIENT_QDRANT_API_KEY
```

```powershell
$env:QDRANT_URL = "https://qdrant.example"
$env:CLIENT_QDRANT_API_KEY = "<api-key>"
$env:OPENROUTER_API_KEY = "<api-key>"
```

A política YAML da coleção define o nome da coleção Qdrant e a variável da
chave OpenRouter. A chave Qdrant é opcional quando o endpoint não exige
autenticação. `QDRANT_URL` é o fallback quando a política e o YAML da coleção
não definem a URL. `poe pipeline --through ingest` usa OpenRouter para gerar
embeddings e reconcilia os pontos; `--through promote` não pode anteceder essa
etapa. Confirme DNS/TLS e alcance de rede do controlador para os dois serviços.

## Checklist

- DNS/TLS e rede privada;
- catálogo e S3 acessíveis pelo controlador;
- result store acessível pelos hosts GPU e pelo cliente;
- OpenRouter e Qdrant acessíveis pelo controlador quando houver ingestão;
- variáveis de segredo presentes no processo;
- relógios sincronizados;
- timeouts e pools dimensionados;
- backups e retenção definidos.

Anterior: [Executar o pipeline](execute-pipeline.md)
Próximo: [Operação e recuperação](operations.md)
Referência: [Configuração](../reference/configuration.md)
Avançado: [Persistência MinerU](../../technical/architecture/mineru-persistence.md)
