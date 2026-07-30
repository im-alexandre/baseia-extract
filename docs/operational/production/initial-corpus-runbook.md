---
id: operational.production.initial-corpus-runbook
title: Bootstrap da coleção inicial BaseIA
kind: how-to
audience: operator
mode: production
stage: inventory
status: current
nav_order: 335
---

# Bootstrap da coleção inicial BaseIA

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

Este é um runbook do corpus inicial deste repositório. Não é um tutorial
genérico para novas coleções.

## Objetivo

Promover o inventário local validado e recriar os manifests sem task IDs, pods,
URLs, tentativas, durações ou configurações de runs antigos.

## Fontes aprovadas

- SNPTEE:
  `D:\backups\snptee\SNPTEE_PDFs\edicoes_anteriores_trabalhos_extraidos`;
- Ciência de Dados: `D:\backups\livros-data-science`;
- Revista PPGCC UERJ: `D:\backups\revista-ppgcc`;
- Minha Dissertação:
  `D:\dissertacao\referencia_PLD_orientador` e
  `D:\dissertacao\referencias`;
- documentos válidos restantes: coleção `Diversos`.

## Regras de organização

- SNPTEE preserva a árvore relativa por ano/grupo;
- sequências de espaços nos nomes SNPTEE são normalizadas para `_` na fonte e
  no corpus;
- as demais coleções ficam planas na raiz de sua coleção;
- os oito PDFs inválidos conhecidos vão para
  `data/bootstrap/quarantine-invalid`;
- referências técnicas do repositório não entram no inventário;
- temporários órfãos ficam em
  `data/bootstrap/quarantine-operational`, nunca no manifesto.

## Estado esperado

| Coleção | Documentos |
| --- | ---: |
| SNPTEE | 2.149 |
| Ciência de Dados | 179 |
| Revista PPGCC UERJ | 201 |
| Minha Dissertação | 62 |
| Diversos | 1.449 |
| **Total válido** | **4.040** |

## Execução

Use uma janela exclusiva, sem processos alterando fontes ou destino:

```powershell
uv run poe bootstrap plan --workers 3
uv run poe bootstrap apply --workers 3
uv run poe render --workers 3
uv run poe bootstrap refresh-manifests --workers 3
uv run poe audit
```

Depois da consolidação:

```powershell
uv run poe bootstrap plan --workers 3
```

O segundo plano deve reconhecer o inventário canônico e produzir
`bootstrap-validation-plan.json`.

## Segurança e retomada

O plano registra checksums e raízes absolutas. O `apply`:

- adquire lock exclusivo;
- revalida hashes antes da primeira mutação;
- mantém journal de fase em
  `data/bootstrap/bootstrap-state.json`;
- preserva o plano inicial em `bootstrap-plan.json`;
- permite retomada observável depois de interrupção.

Não remova quarentenas ou evidências de origem antes de validar a promoção S3
e o catálogo.

## Próxima etapa

Publique e ative com:

```powershell
uv run poe promote-s3 plan
uv run poe promote-s3 apply
```

Anterior: [Publicar e ativar a coleção](collection-bootstrap.md)
Próximo: [Executar o pipeline](execute-pipeline.md)
Avançado: [TODO de bootstrap genérico](../../technical/backlog/generic-collection-bootstrap.md)
