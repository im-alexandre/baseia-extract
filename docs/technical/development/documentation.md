---
id: technical.development.documentation
title: Manutenção da documentação
kind: development
audience: maintainer
mode: all
stage: documentation
status: current
nav_order: 581
---

# Manutenção da documentação

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md)

## Governança

A documentação é viva, mas não é atualizada como efeito colateral. Conforme
`AGENTS.md`, agentes só podem modificar `README.md`, `SOUL.md` ou `docs/`
quando o usuário solicitar diretamente uma atualização ou alteração
documental.

Quando uma mudança de código criar possível drift sem autorização documental:

1. não altere a documentação;
2. registre a divergência no relatório final;
3. solicite autorização explícita para corrigi-la.

Esta regra mantém a evolução documental sob decisão do usuário sem permitir
que divergências conhecidas passem despercebidas.

## Separação física

```text
docs/
├── operational/    tutoriais, how-to e referência de utilização
└── technical/      estrutura, arquitetura, conceitos e desenvolvimento
```

A documentação operacional é segmentada por ambiente:

```text
operational/
├── local/
├── cataloged-development/
├── production/
└── reference/
```

## Metadados semânticos

Todo documento em `docs/` começa com YAML front matter:

```yaml
---
id: operational.local.inventory
title: Primeiro inventário
kind: tutorial
audience: user
mode: local
stage: inventory
status: current
nav_order: 130
---
```

| Campo | Contrato |
| --- | --- |
| `id` | identificador global estável e único |
| `title` | título para navegação |
| `kind` | `index`, `tutorial`, `how-to`, `reference`, `concept`, `architecture`, `development`, `backlog` ou `backlog-item` |
| `audience` | público principal |
| `mode` | ambiente ao qual se aplica |
| `stage` | etapa ou domínio |
| `status` | `current`, `todo`, `future` ou `deprecated` |
| `nav_order` | ordenação dentro do portal |

Esses metadados permitem que uma futura rota construa menus sem inferir
semântica a partir do path ou do texto.

## Estrutura Markdown

- exatamente um `# H1`;
- headings em ordem, sem saltar níveis;
- fenced code com linguagem;
- tabelas para mapeamentos, não para layout visual;
- links relativos;
- sem HTML de apresentação;
- títulos de seções estáveis;
- navegação global depois do H1;
- anterior, próximo e conteúdo relacionado no rodapé.

Tutoriais operacionais devem explicitar, quando aplicável:

- o que é;
- para que serve e quando usar;
- pré-requisitos;
- entrada;
- comando;
- saída;
- verificação;
- falhas e recuperação;
- próxima etapa;
- referência técnica relacionada.

## Evitar drift

Ao receber autorização para atualizar documentação:

1. compare tasks com `pyproject.toml`;
2. compare defaults com código, `.env.example` e Compose;
3. confira endpoints e healthchecks na implementação;
4. marque explicitamente recursos futuros;
5. não documente comandos inexistentes;
6. valide todos os links relativos;
7. verifique unicidade de `id` e coerência do front matter.

## SOUL.md

`SOUL.md` é um artefato de primeira classe preservado integralmente. Não o
normalize nem o reescreva como parte de manutenção editorial. Documentos
derivados podem organizar seus princípios por links.

Anterior: [Guia de desenvolvimento](guide.md)
Próximo: [Soft backlog](../backlog/README.md)
Operação relacionada: [Portal de utilização](../../operational/README.md)
