# BaseIA Extract

Camada de extração documental do BaseIA.

O código operacional vive em `src/baseia_extract`. Configuração de ambiente fica no `.env`; caminhos e defaults são resolvidos exclusivamente por `baseia_extract.settings`.

## Instalação

```powershell
uv sync
Copy-Item .env.example .env
```

Edite o `.env` com o diretório do corpus e as URLs públicas dos pods MinerU.

## Pipeline operacional

### 1. Inventário da coleção

```powershell
uv run poe inventory
```

Sobrescritas ocasionais:

```powershell
uv run poe inventory --corpus 'D:\meu-corpus' --workers 8
```

### 2. Amostra da coleção

```powershell
uv run poe sample --size 100
```

A task usa seed fixa por padrão e grava `data/inventory/sample.csv`.

### 3. Extração MinerU

```powershell
uv run poe extract
```

A concorrência total é:

```text
quantidade de pods × MINERU_WORKERS_PER_POD
```

Exemplo para uma RTX 5090 configurada para 12 chamadas concorrentes:

```powershell
uv run poe extract --workers-per-pod 12
```

Teste limitado:

```powershell
uv run poe extract --limit 20
```

Reprocessamento:

```powershell
uv run poe extract --overwrite
```

## Saídas canônicas

```text
data/inventory/inventory.csv
artifacts/mineru/extraction/documents/
artifacts/mineru/extraction/runs.csv
artifacts/mineru/extraction/errors.csv
artifacts/mineru/extraction/summary.json
artifacts/mineru/extraction/pods.json
artifacts/ir/
artifacts/structure/
artifacts/chunks/
```

Não há configuração de caminhos dentro das etapas do pipeline. Novos módulos devem importar `settings` de `baseia_extract.settings`.
