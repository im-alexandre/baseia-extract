---
id: technical.development.guide
title: Guia de desenvolvimento
kind: development
audience: maintainer
mode: all
stage: development
status: current
nav_order: 580
---

# Guia de desenvolvimento

[Documentação](../../README.md) · [Uso](../../operational/README.md) ·
[Local](../../operational/local/README.md) ·
[Dev catalogado](../../operational/cataloged-development/README.md) ·
[Produção](../../operational/production/README.md) ·
[Documentação técnica](../README.md)

## Preparar o ambiente

```powershell
uv sync
uv run poe --help
```

Leia primeiro:

1. [Estrutura do repositório](../repository-structure.md);
2. [Visão geral da arquitetura](../architecture/overview.md);
3. o conceito ou adapter diretamente relacionado à mudança.

## Princípios

- library-first: consulte utilitários internos, dependências existentes,
  runtime instalado e documentação oficial antes de implementar;
- preserve o modo local sem serviços obrigatórios para as etapas que já são
  locais;
- mantenha dados, inventários, amostras e artefatos no diretório da coleção,
  nunca na worktree;
- trate `baseia.collection.yaml` como configuração não secreta e `.baseia/`
  como estado operacional da coleção;
- referencie credenciais por nomes de variáveis de ambiente; não grave
  segredos no YAML da coleção;
- trate path como identidade lógica e SHA-256 como integridade/revisão;
- escreva objetos antes de metadados de conclusão;
- mantenha o catálogo como único writer de metadados;
- mantenha o render como único produtor do Markdown canônico;
- não promova metadados operacionais de desenvolvimento;
- não transforme S3 em fila ou lock.

## Percurso de uma alteração

1. localize o entry point em `pyproject.toml`;
2. siga o mapa de módulos da
   [estrutura do repositório](../repository-structure.md);
3. identifique o contexto da coleção e os invariantes persistidos;
4. se a mudança alcançar serviços, mantenha separados o S3 intermediário do
   MinerU e o S3 canônico do catálogo;
5. consulte a documentação da biblioteca ou runtime;
6. faça a menor mudança coerente;
7. valide proporcionalmente ao risco;
8. atualize documentação somente quando o usuário tiver solicitado
   diretamente.

## Validações proporcionais

Para Python e infraestrutura:

```powershell
uv run python -m compileall -q src infra
docker compose --profile catalog config
git diff --check
```

Quando Docker, S3 e PostgreSQL estiverem disponíveis, prefira smoke tests reais
de migration, health, upload/HEAD/download e concorrência de `get-or-create`.

Não adicione testes unitários baseados em mocks que apenas repetem strings,
configurações ou CLIs. Testes devem proteger comportamento relevante.

## Banco e migrations

Modelos ficam em `src/baseia_extract/catalog/models.py`. Migrations ficam em
`infra/catalog/migrations/versions/`.

No host:

```powershell
uv run poe catalog-migrate
```

No container, `infra/catalog/start.sh` executa a migration automaticamente
antes de iniciar Uvicorn.

## MinerU

Antes de alterar `infra/mineru`:

1. confira `MINERU_VERSION`;
2. inspecione o wheel instalado;
3. consulte a documentação oficial;
4. identifique APIs privadas interceptadas;
5. execute build e smoke test com GPU.

O patch deve falhar para versões desconhecidas e não absorver regras canônicas
de catálogo ou storage.

## Dívidas conhecidas

Necessidades ainda sem solução consolidada pertencem ao
[soft backlog técnico](../backlog/README.md), não aos tutoriais operacionais.

Anterior: [Artefatos e layout](../concepts/artifacts.md)
Próximo: [Manutenção da documentação](documentation.md)
Operação relacionada: [Referência operacional](../../operational/reference/README.md)
