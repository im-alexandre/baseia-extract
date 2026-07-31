---
id: technical.backlog.home
title: Soft backlog técnico
kind: backlog
audience: maintainer
mode: all
stage: backlog
status: current
nav_order: 590
---

# Soft backlog técnico

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md)

Esta seção registra necessidades técnicas conhecidas que ainda não possuem uma
solução consolidada. Ela não é um cronograma, não promete implementação e não
deve antecipar uma arquitetura definitiva.

Cada item descreve:

- a necessidade observada;
- o impacto;
- o resultado que falta alcançar;
- limites do registro.

## Itens

| ID | Necessidade | Estado |
| --- | --- | --- |
| `CAP-001` | [Tornar explícito o modelo de concorrência e capacidade](concurrency-model.md) | TODO |
| `CAT-001` | [Generalizar promoção de coleções](generic-collection-bootstrap.md) | concluído |
| `CTX-001` | [Agrupar coleções em workspaces e perfis](workspace-contexts.md) | TODO |
| `CAT-002` | [Transferir a autoridade inicial para S3 antes do processamento](production-authority-handoff.md) | TODO |
| `SEM-001` | [Cobrir tipos semânticos MinerU como `index`](semantic-block-types.md) | TODO |
| `OPS-001` | [Formalizar a estratégia promovível](promotable-strategy.md) | TODO |
| `ORC-001` | [Implementar orquestração de produção](production-orchestration.md) | TODO |
| `ING-001` | [Chunking, embeddings e Qdrant](qdrant-ingestion.md) | concluído (histórico) |

Itens só devem ser adicionados ou alterados quando o usuário solicitar
diretamente uma atualização documental, conforme `AGENTS.md`.

Anterior: [Índice técnico](../README.md)
Próximo: [CAP-001 — Concorrência e capacidade](concurrency-model.md)
Operação relacionada: [Referência de configuração](../../operational/reference/configuration.md)
