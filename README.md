# BaseIA Extract

Camada de extração documental do BaseIA.

O código operacional vive em `src/baseia_extract`. A configuração fica no
`.env`; caminhos e defaults são resolvidos exclusivamente por
`baseia_extract.settings`.

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
mineru-server/          imagem e bootstrap da API MinerU remota
```

Por padrão, o corpus fica em `corpus/`. Todos os resultados ficam abaixo de
`data/`.

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

### 3. Auditoria

```powershell
poe audit
```

Antes da extração, a task valida o inventário, deduplica por `document_id` e
gera:

```text
data/audit/inventory/extraction_manifest.csv
data/audit/inventory/invalid_documents.csv
data/audit/inventory/duplicate_documents.csv
data/audit/inventory/summary.json
```

Depois da extração, a mesma task também verifica os `middle.json`, compara
páginas, consolida o schema observado e gera:

```text
data/audit/extraction/documents.csv
data/audit/extraction/failures.csv
data/audit/extraction/warnings.csv
data/audit/extraction/retry_manifest.csv
data/audit/extraction/schema_observed.json
data/audit/extraction/outliers.csv
data/audit/extraction/review_sample.csv
data/audit/extraction/summary.json
```

A auditoria não sobe GPU nem cria pods.

### 4. Extração completa

```powershell
poe extract
```

A task:

1. audita o inventário e usa apenas documentos válidos e únicos;
2. resolve o template privado do RunPod pelo nome;
3. cria a quantidade configurada de pods;
4. injeta versão, porta e concorrência do MinerU em cada pod;
5. aguarda `/openapi.json` expor o contrato real do `mineru-api`;
6. processa todo o manifesto deduplicado;
7. persiste continuamente o progresso;
8. encerra os pods em `finally`;
9. executa a auditoria completa sem GPU.

Não existe modo limitado na task operacional. `poe extract` sempre processa
todo o manifesto, pulando documentos já concluídos quando
`MINERU_OVERWRITE=false`.

A concorrência total é:

```text
RUNPOD_POD_COUNT × MINERU_WORKERS_PER_POD
```

`MINERU_WORKERS_PER_POD` também é enviado para
`MINERU_API_MAX_CONCURRENT_REQUESTS` no servidor. O cliente e o pod, portanto,
usam o mesmo limite.

## Servidor MinerU no RunPod

A imagem em `mineru-server/` contém somente o sistema operacional, CUDA/PyTorch
da imagem-base, bibliotecas nativas e o bootstrap. O ambiente Python do MinerU
e os modelos `pipeline` ficam no volume compartilhado montado em `/workspace`.

Na primeira execução de uma versão, um pod:

1. cria `/workspace/.venv`;
2. instala `mineru[pipeline]==MINERU_VERSION`;
3. baixa somente os modelos do backend `pipeline`;
4. grava marcadores versionados no volume.

Os demais pods aguardam os locks no volume. Nas execuções seguintes, o ambiente
e os modelos são reutilizados.

O template privado do RunPod deve:

- apontar para a imagem construída com `mineru-server/Dockerfile`;
- montar o network volume em `/workspace`;
- expor `8000/http`;
- deixar **Docker Entrypoint** e **Docker Start Command** vazios.

O último requisito é importante: um entrypoint configurado no template
sobrescreve o entrypoint da imagem e pode iniciar o servidor OpenAI do vLLM no
lugar do `mineru-api`.

O provisionador não considera mais qualquer `/health` como sucesso. Ele exige as
rotas `/tasks`, `/tasks/{task_id}`, `/tasks/{task_id}/result` e `/file_parse`.
Caso outro serviço — por exemplo, o vLLM — ocupe a porta 8000, a execução falha
imediatamente e os pods são encerrados.

## Saídas canônicas

```text
data/inventory/
data/mineru/documents/
data/mineru/runs.csv
data/mineru/errors.csv
data/mineru/summary.json
data/mineru/pods.json
data/audit/inventory/
data/audit/extraction/
data/ir/
data/structure/
data/chunks/
```

## Sobrescrita

O comportamento é controlado somente no `.env`:

```env
MINERU_OVERWRITE=false
```

Com `false`, documentos já concluídos e válidos são preservados e ignorados.
Com `true`, suas saídas são removidas e recriadas.
