# BaseIA Extract

Camada de extração documental do BaseIA.

O código operacional vive em `src/baseia_extract`. A configuração fica no `.env`; caminhos e defaults são resolvidos exclusivamente por `baseia_extract.settings`.

## Instalação

```powershell
uv sync
Copy-Item .env.example .env
```

O Poe the Poet é usado globalmente e não faz parte das dependências do projeto.

## Estrutura local

```text
corpus/                 PDFs da coleção; ignorado pelo Git
data/                   todos os dados produzidos; ignorado pelo Git
src/baseia_extract/     código Python do pipeline
```

Por padrão, o corpus fica em `corpus/`. Todos os resultados ficam abaixo de `data/`.

## Pipeline operacional

### 1. Inventário completo

```powershell
poe inventory
```

Opcionalmente, ajuste apenas o paralelismo local:

```powershell
poe inventory --workers 8
```

Saída:

```text
data/inventory/inventory.csv
data/inventory/inventory_errors.csv
```

### 2. Amostra reprodutível

```powershell
poe sample --size 100
```

Saída:

```text
data/inventory/sample.csv
```

### 3. Extração completa

```powershell
poe extract
```

A task:

1. resolve o template privado do RunPod pelo nome;
2. cria a quantidade configurada de pods;
3. aguarda o MinerU responder em `/health`;
4. processa todo o `data/inventory/inventory.csv`;
5. persiste continuamente o progresso;
6. encerra os pods em `finally`.

Não existe modo limitado na task operacional. `poe extract` sempre processa o manifesto completo, pulando documentos já concluídos quando `MINERU_OVERWRITE=false`.

A concorrência total é:

```text
RUNPOD_POD_COUNT × MINERU_WORKERS_PER_POD
```

## Saídas canônicas

```text
data/inventory/
data/mineru/documents/
data/mineru/runs.csv
data/mineru/errors.csv
data/mineru/summary.json
data/mineru/pods.json
data/ir/
data/structure/
data/chunks/
```

## Sobrescrita

O comportamento é controlado somente no `.env`:

```env
MINERU_OVERWRITE=false
```

Com `false`, documentos já concluídos são preservados e ignorados. Com `true`, suas saídas são removidas e recriadas.
