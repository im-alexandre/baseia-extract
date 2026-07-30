---
id: operational.cataloged.extraction
title: Extrair com persistência
kind: tutorial
audience: operator
mode: cataloged-development
stage: extract
status: current
nav_order: 230
---

# Extrair com persistência

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) · [Dev catalogado](README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

O adapter MinerU aceita a task por chave idempotente, executa o parser e
persiste o pacote no S3 antes de declarar sucesso. O cliente troca referências
duráveis; ele só baixa intermediários quando o render local precisa
materializá-los.

## Persistir endpoints na coleção

```powershell
uv run poe collection configure "Acme Diagnóstico" `
    --api-url "https://gpu-a.example" `
    --api-url "https://gpu-b.example"
```

Execute:

```powershell
uv run poe pipeline `
    --collection "Acme Diagnóstico" `
    --through extract `
    --workers 3
```

As URLs passadas diretamente a `pipeline` valem somente para a execução; as
URLs gravadas por `collection configure` ficam no YAML.

## Result store do GPU

O servidor pode persistir no mesmo S3 canônico ou em um store próprio. Quando
for diferente, configure endpoint, bucket esperado e nomes das variáveis de
credencial:

```powershell
$env:GPU_S3_ACCESS_KEY = "<access-key>"
$env:GPU_S3_SECRET_KEY = "<secret-key>"

uv run poe collection configure "Acme Diagnóstico" `
    --mineru-result-s3-endpoint-url "https://gpu-results.example" `
    --mineru-result-s3-bucket "mineru-results" `
    --mineru-result-s3-access-key-env "GPU_S3_ACCESS_KEY" `
    --mineru-result-s3-secret-key-env "GPU_S3_SECRET_KEY"
```

O endpoint deve ser a URL que o cliente consegue alcançar; a URL interna usada
pelo container GPU pode ser diferente.

## Inspecionar

```powershell
Get-Content -Raw `
    "D:/clientes/acme/documentos/.baseia/extraction/summary.json"
Get-Content -Raw `
    "D:/clientes/acme/documentos/.baseia/audit/extraction/summary.json"
```

`remote_artifact_uri_count` confirma quantas tasks têm referência remota. Uma
resposta perdida deve ser reconciliada antes de qualquer reenvio.

Anterior: [Inventariar e promover](inventory.md)
Próximo: [Renderizar e publicar](rendering.md)
Referência: [Configuração MinerU](../reference/configuration.md#mineru-e-extract)
Avançado: [Persistência MinerU](../../technical/architecture/mineru-persistence.md)
