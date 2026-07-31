---
id: operational.production.strategy
title: Promover a estratégia
kind: tutorial
audience: operator
mode: production
stage: promotion
status: current
nav_order: 310
---

# Promover a estratégia

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## Objetivo

Reproduzir decisões aprovadas em um ambiente limpo sem transportar estado
operacional de desenvolvimento.

## Leve para produção

- commit e imagens fixados;
- MinerU e backend escolhidos;
- opções de OCR/parsing;
- versão e regras de render;
- critérios de auditoria;
- política de ingestão (chunking, embedding e coleção Qdrant);
- requisitos de hardware e topologia;
- nome e versão lógica da estratégia.

## Recrie em produção

- `baseia.collection.yaml`;
- inventário e amostra;
- manifests de documento;
- snapshots S3;
- stage runs, leases e task IDs;
- endpoints e credenciais do ambiente.

## Procedimento atual

Ainda não há `poe promote-strategy`. Registre a decisão, crie configuração e
segredos novos, faça um smoke por amostra e só então execute a coleção
integral:

```powershell
uv run poe init "E:/entregas/acme/documentos" `
    --name "Acme Produção" `
    --mode production `
    --resource-scope client `
    --topology distributed `
    --through promote `
    --execute register
```

Antes de executar `pipeline --through promote`, complete o YAML criado com a
política aprovada e deixe as credenciais no ambiente do controlador:

```yaml
strategy:
  name: acme-production
  version: "1"
  ingest_policy: .baseia/embedding.yaml
```

`strategy` já aceita `name`, `version` e `ingest_policy`; o pacote declarativo
mais amplo e validado de estratégia está no
[soft backlog](../../technical/backlog/promotable-strategy.md).

Anterior: [Produção](README.md)
Próximo: [Ambiente com Compose](compose-environment.md)
Avançado: [Arquitetura e modos](../../technical/architecture/overview.md)
