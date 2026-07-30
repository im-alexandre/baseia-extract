---
id: technical.backlog.semantic-block-types
title: "TODO SEM-001: cobertura de tipos semânticos MinerU"
kind: backlog-item
audience: maintainer
mode: all
stage: render
status: todo
nav_order: 595
---

# TODO SEM-001: cobertura de tipos semânticos MinerU

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Documentação técnica](../README.md) · [Soft backlog](README.md)

## Evidência observada

Uma validação de três PDFs e 609 páginas encontrou 27 blocos MinerU do tipo
`index` em um documento de referência DAX. As páginas eram sumário, índice
remissivo ou front matter; scores de detecção estavam entre aproximadamente
0,98 e 0,99. Não houve diferença de páginas nem spans desconhecidos.

## Comportamento atual

- auditoria emite `unknown_block_types=index`;
- o IR preserva o bloco e seus atributos;
- a estrutura mapeia o papel para `OTHER`;
- o Markdown canônico exclui esse conteúdo do fluxo primário.

Isso é um aviso de cobertura taxonômica, não corrupção.

## Resultado que falta

- decidir se `index` é tipo conhecido ou família com subtipos;
- definir inclusão no fluxo principal por contexto;
- diferenciar sumário, índice remissivo e front matter;
- adicionar fixtures comportamentais apenas quando houver regra semântica
  aprovada.

Anterior: [CAT-002 — Autoridade](production-authority-handoff.md)
Próximo: [OPS-001 — Estratégia](promotable-strategy.md)
Operação relacionada: [Auditoria](../../operational/local/audit-and-recovery.md)
