---
id: operational.production.execute
title: Executar o pipeline em produção
kind: tutorial
audience: operator
mode: production
stage: end-to-end
status: current
nav_order: 340
---

# Executar o pipeline em produção

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Pré-condições

- coleção registrada com escopo diferente de `unassigned`;
- catálogo e S3 canônico saudáveis;
- um ou mais endpoints MinerU;
- result store acessível pelo cliente;
- estratégia e versões fixadas.

## Executar

```powershell
uv run poe pipeline `
    --collection "Acme Produção" `
    --through promote `
    --workers 3
```

Se as URLs não estiverem no YAML:

```powershell
uv run poe pipeline `
    --collection "Acme Produção" `
    --through promote `
    --api-url "https://gpu-a.example" `
    --api-url "https://gpu-b.example"
```

`inventory`, `extract`, `render` e `promote` são checkpoints. Escolher uma
etapa executa ou reconcilia todas as anteriores. O relatório final fica em
`.baseia/pipeline/latest.json`.

## Retomar

Repita o mesmo comando. Tasks MinerU são reconciliadas por identidade,
canônicos atuais são ignorados e a promoção idêntica valida e reutiliza o
snapshot.

Para reler as fontes antes:

```powershell
uv run poe pipeline `
    --collection "Acme Produção" `
    --through promote `
    --refresh
```

## Acompanhar o controlador de baixo nível

Durante uma extração longa iniciada pelo fluxo legado:

```powershell
uv run poe extract status
uv run poe extract watch
uv run poe extract stop
```

O pipeline de coleção usa um lock por coleção e registra relatórios, mas ainda
é coordenado pelo processo CLI. Workflows Temporal permanecem futuros.

Anterior: [Registrar e ativar a coleção](collection-bootstrap.md)
Próximo: [Usar serviços externos](external-services.md)
Referência: [Comandos](../reference/commands.md)
Avançado: [Concorrência e idempotência](../../technical/architecture/catalog.md)
