---
id: operational.local.installation
title: Instalação local
kind: tutorial
audience: user
mode: local
stage: installation
status: current
nav_order: 120
---

# Instalação local

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](README.md) · [Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é

Esta etapa cria o ambiente Python reproduzível e prepara a configuração local.

## Quando usar

Use na primeira execução, depois de atualizar `uv.lock` ou ao recriar a
`.venv`.

## Pré-requisitos

- Windows;
- PowerShell 7;
- Python 3.12 ou superior;
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/);
- Git, caso o projeto tenha sido obtido por clone.

Verifique o ambiente:

```powershell
pwsh --version
python --version
uv --version
```

## Instalar as dependências

Na raiz do repositório:

```powershell
uv sync
uv run poe --version
uv run poe --help
```

`uv sync` instala o projeto, as dependências travadas em `uv.lock` e o Poe
declarado no grupo de desenvolvimento. A forma documentada e reprodutível de
executar tasks é `uv run poe <task>`.

## Criar a configuração local

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Não sobrescreva um `.env` existente sem revisar seus endpoints, credenciais e
paths. `.env.example` contém apenas defaults de desenvolvimento.

## Saída

- `.venv/` com o ambiente resolvido;
- `.env` local, quando ainda não existia;
- tasks disponíveis em `pyproject.toml`.

## Verificar

```powershell
uv run python -c "import baseia_extract; print('BaseIA disponível')"
uv run poe --help inventory
```

## Falhas comuns

| Sintoma | Verificação |
| --- | --- |
| `uv` não encontrado | instale o `uv` e abra um novo PowerShell |
| Python incompatível | confira `.python-version` e `python --version` |
| `poe` não encontrado | use `uv sync` e execute como `uv run poe` |
| configuração inesperada | compare `.env` com `.env.example` sem copiar credenciais |

Anterior: [Quick Start](quickstart.md)
Próximo: [Primeiro inventário](inventory.md)
Referência: [Configuração](../reference/configuration.md)
Avançado: [Guia de desenvolvimento](../../technical/development/guide.md)
