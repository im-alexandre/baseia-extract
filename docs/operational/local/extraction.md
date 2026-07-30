---
id: operational.local.extraction
title: Primeira extração
kind: tutorial
audience: user
mode: local
stage: extract
status: current
nav_order: 150
---

# Primeira extração

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é

A extração envia PDFs válidos a um backend MinerU e materializa os
intermediários exigidos pelo render. O Markdown MinerU é diagnóstico
intermediário, não documento canônico.

## Escolher o backend

| Opção | Exemplo | Obrigatória? |
| --- | --- | --- |
| processo no host | `http://127.0.0.1:8000` | uma URL de parser é necessária |
| container local com GPU | perfil `gpu` do Compose | não |
| servidor externo | `https://mineru.example` | não |
| várias URLs | repita `--api-url` | não |

O próprio servidor com várias GPUs pode executar o `mineru-router`. O cliente
distribui entre várias URLs; não é necessário um router central adicional.

Verifique o adapter:

```powershell
$MineruUrl = "http://127.0.0.1:8000"
Invoke-RestMethod "$MineruUrl/baseia-capabilities"
Invoke-RestMethod "$MineruUrl/baseia-persistence-health"
```

## Extrair a amostra

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through extract `
    --sample `
    --api-url $MineruUrl `
    --workers 3
```

Entrada: amostra validada, PDFs e URL saudável.
Saídas:

- `arquivo/intermediate/mineru/`;
- `arquivo/manifest.json`;
- `.baseia/extraction/`;
- `.baseia/audit/extraction/`;
- `.baseia/pipeline/latest.json`.

## Extrair toda a coleção

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through extract `
    --api-url $MineruUrl
```

## Result store separado

O storage canônico da coleção e o storage de resultados de um servidor GPU
podem ser diferentes. Configure o endpoint acessível pelo cliente e apenas os
nomes das variáveis de credencial:

```powershell
$env:GPU_S3_ACCESS_KEY = "<access-key>"
$env:GPU_S3_SECRET_KEY = "<secret-key>"

uv run poe collection configure "Artigos" `
    --mineru-result-s3-endpoint-url "http://127.0.0.1:9000" `
    --mineru-result-s3-bucket "baseia-gpu-inference" `
    --mineru-result-s3-access-key-env "GPU_S3_ACCESS_KEY" `
    --mineru-result-s3-secret-key-env "GPU_S3_SECRET_KEY"
```

O YAML grava os nomes `GPU_S3_ACCESS_KEY` e `GPU_S3_SECRET_KEY`, nunca seus
valores. Se o result store for o mesmo S3 canônico, nenhuma configuração
adicional é necessária.

## Vários servidores

```powershell
uv run poe pipeline `
    --collection "Artigos" `
    --through extract `
    --api-url "https://mineru-a.example" `
    --api-url "https://mineru-b.example" `
    --workers 3
```

Três é a capacidade inicial do cliente por endpoint neste comando; ajuste
segundo os serviços e o hardware. Esse número não equivale diretamente ao
número de GPUs.

## Recuperar sem reenviar

Para o fluxo de baixo nível, inspecione antes de materializar:

```powershell
uv run poe recover-extract $MineruUrl
uv run poe recover-extract $MineruUrl --apply
```

Uma desconexão não prova falha. O backend persiste a task por chave
idempotente e o cliente reconcilia o resultado antes de reenviar.

Anterior: [Primeira amostragem](sampling.md)
Próximo: [Primeiro render](rendering.md)
Referência: [Comandos de extração](../reference/commands.md)
Avançado: [Persistência MinerU](../../technical/architecture/mineru-persistence.md)
