---
id: operational.home
title: Utilização do BaseIA
kind: index
audience: user
mode: all
stage: navigation
status: current
nav_order: 10
---

# Utilização do BaseIA

[Documentação](../README.md) · [Local](local/README.md) ·
[Dev catalogado](cataloged-development/README.md) ·
[Produção](production/README.md) · [Referência](reference/README.md) ·
[Documentação técnica](../technical/README.md)

Esta é a documentação principal para operar o framework. Cada ambiente possui
um percurso completo, com entradas, comandos, saídas e critérios de
verificação.

Em todos os ambientes, uma **coleção** é o contexto operacional estável:
origens em disco, modo, topologia, recursos e estágio alcançado. O comando
`poe collection` permite selecionar esse contexto; `poe init` registra uma
origem sem copiá-la para a worktree; `poe pipeline` avança a coleção; e
`poe quick` incorpora documentos urgentes até o estágio já alcançado.

## Escolha o ambiente

| Ambiente | Use quando | Comece em |
| --- | --- | --- |
| Local | estiver conhecendo uma coleção, criando amostras ou experimentando parsers | [Quick Start local](local/quickstart.md) |
| Dev catalogado | precisar de catálogo, S3, idempotência e histórico operacional de desenvolvimento | [Preparar o ambiente](cataloged-development/environment.md) |
| Produção | já tiver uma estratégia definida e quiser recriar registros limpos e executar em escala | [Produção](production/README.md) |

Os modos não impõem uma infraestrutura rígida. Uma execução local pode usar
URLs MinerU externas; uma coleção catalogada pode usar serviços locais ou
remotos. Modo descreve o grau de persistência e governança, enquanto topologia
descreve onde os serviços executam.

## Regra de promoção

O conhecimento obtido em desenvolvimento pode orientar a estratégia de
produção. Runs, task IDs, tentativas, URLs temporárias e manifests
experimentais não são promovidos automaticamente. Consulte
[Promover a estratégia](production/promoting-the-strategy.md).

## Referência transversal

- [Comandos](reference/commands.md)
- [Configuração](reference/configuration.md)
- [Artefatos e saídas](reference/artifacts.md)

Próximo: [Quick Start local](local/quickstart.md)
Avançado: [Documentação técnica](../technical/README.md)
