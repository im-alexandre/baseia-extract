---
id: technical.backlog.concurrency-model
title: "TODO CAP-001: modelo de concorrência e capacidade"
kind: backlog-item
audience: maintainer
mode: all
stage: capacity
status: todo
nav_order: 591
---

# TODO CAP-001: modelo de concorrência e capacidade

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Necessidade

Tornar inequívoco o significado de concorrência e capacidade em cada camada
do framework.

## Problema observado

O termo `workers` é usado para recursos diferentes:

- paralelismo local de inventário, bootstrap e render;
- capacidade inicial do cliente por URL MinerU;
- alterações de admissão aplicadas com `extract scale`.

Ao mesmo tempo, outras variáveis controlam:

- limite agregado do router e limites por GPU;
- janela de processamento MinerU;
- workers de persistência;
- transfers S3 por publicação;
- downloads de materialização;
- pool de conexões HTTP;
- concorrência da publicação do render;
- concorrência global do artifact store.

Esses valores estão distribuídos entre `pyproject.toml`, `settings.py`,
`.env.example`, Compose e entrypoint MinerU. Um número com o mesmo nome não
representa necessariamente a mesma unidade, o mesmo gargalo ou o mesmo
recurso.

## Impacto

- operadores podem interpretar capacidade do cliente como quantidade de GPUs;
- defaults podem divergir entre CLI, configuração e serviço;
- aumentar um knob pode apenas deslocar o gargalo para S3, catálogo, disco ou
  pool HTTP;
- a capacidade efetiva de múltiplos endpoints não fica evidente;
- diagnósticos de performance e backpressure exigem conhecimento implícito do
  código.

## Resultado que falta alcançar

- vocabulário único para cada tipo de capacidade;
- unidade e escopo explícitos para cada configuração;
- defaults definidos em fontes de verdade identificáveis;
- exibição da configuração efetiva no início da execução;
- distinção clara entre admissão, processamento, persistência e transferência;
- forma observável de relacionar limites do cliente com capacidades anunciadas
  pelos endpoints;
- orientação de dimensionamento baseada em métricas do ambiente.

## Fora deste TODO

Este registro não escolhe nomes, fórmulas, algoritmo de autotune, biblioteca de
fila nem arquitetura de scheduling. Essas decisões exigem investigação e
benchmark separados.

Anterior: [Soft backlog](README.md)
Próximo: [CAT-001 — Bootstrap genérico](generic-collection-bootstrap.md)
Operação relacionada: [Comandos](../../operational/reference/commands.md)
Arquitetura relacionada: [Persistência MinerU](../architecture/mineru-persistence.md)
