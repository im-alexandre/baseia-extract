# BaseIA Extract

Extração de PDFs por serviços HTTP `mineru-api` ou `mineru-router`.

## Instalação

```powershell
uv sync
Copy-Item .env.example .env
```

Cada documento possui um PDF canônico e um único diretório de artefatos,
identificado por seu caminho original. O manifesto atômico fica dentro desse
diretório. A fila, a ocupação e o inventário dos endpoints existem somente
durante a execução.

## Comandos

```powershell
poe inventory
poe sample --size 100
poe audit
poe extract
poe render
```

`poe extract` roda no terminal e apresenta um painel Rich com:

- concluídos, reutilizados, em voo, retries, erros e pendentes;
- saúde, capacidade, ocupação e ociosidade por endpoint;
- capacidade anunciada pela API e limite efetivo do cliente;
- fila interna anunciada pelo `/health` do MinerU.

O prazo de confirmação no Volume é no mínimo `MINERU_TASK_TIMEOUT_SECONDS`,
com cinco minutos adicionais para a cópia atômica; o padrão de
`MINERU_RESULT_TIMEOUT_SECONDS` é 3600 segundos. Um timeout mantém o `task_id`
no manifesto para retomada, sem novo envio do PDF.

O terminal não imprime o nome de cada documento. Um log textual com snapshots
periódicos é gravado no diretório temporário mostrado no início.

Configure o endpoint padrão no `.env`:

```text
MINERU_API_URL=http://127.0.0.1:8000
```

Sem URL na linha de comando, `poe extract` usa esse valor. Para controlar uma
execução ativa em outro terminal:

```powershell
poe extract status
poe extract log
poe extract add https://mineru-a.example.com --workers 16
poe extract scale https://mineru-a.example.com --workers 32
poe extract stop
```

Somente URLs HTTP(S) são aceitas. IDs de pod e o ciclo de vida da
infraestrutura não fazem parte do comando de extração.

`poe extract stop` encerra o despacho de documentos novos, espera os que estão
em voo (incluindo seus retries) e encerra somente o cliente local. Nenhum
serviço remoto é iniciado, parado ou removido.

`poe render` pode rodar depois ou em paralelo com a extração. Ele percorre o
inventário, processa somente documentos cujo `middle.json` já está disponível
e gera:

```text
data/documents/path/documento.pdf
data/documents/path/documento/manifest.json
data/documents/path/documento/mineru/
data/documents/path/documento/document_ir.json
data/documents/path/documento/structure.json
data/documents/path/documento/document.md
data/documents/path/documento/render.json
data/render_summary.json
```

O Markdown mantém a hierarquia, imagens, tabelas, fórmulas e demais elementos
do fluxo canônico. HTML extraído pelo MinerU é convertido com `markdownify`.
Documentos ainda sem `middle.json` ficam `pending`; referências a assets que
a extração ainda não terminou de gravar ficam `incomplete` e são reavaliadas
na próxima execução. Esta etapa não faz chunking nem embeddings.

Para forçar a reconstrução dos artefatos:

```powershell
poe render --workers 4 --overwrite
```

## Estado e deduplicação

O manifesto é deduplicado pelo SHA-256 completo. Antes de despachar um PDF, o
cliente valida o artefato existente. Um resultado válido é reutilizado e seu
estado é reconciliado no manifesto individual; nomes ou caminhos diferentes para o mesmo
conteúdo não causam nova extração.

Após a deduplicação, o despacho é ordenado pelo SHA-256 completo: uma mistura
determinística do corpus que evita concentrar documentos grandes no fim.

O layout canônico é:

```text
data/documents/<caminho relativo>/<nome>.pdf
data/documents/<caminho relativo>/<nome>/manifest.json
data/documents/<caminho relativo>/<nome>/mineru/
data/documents/<caminho relativo>/<nome>/document_ir.json
data/documents/<caminho relativo>/<nome>/structure.json
data/documents/<caminho relativo>/<nome>/document.md
data/documents/<caminho relativo>/<nome>/render.json
data/extraction/runs.csv
data/extraction/errors.csv
data/extraction/summary.json
data/extraction/endpoints.json
data/extraction/reconciliation.csv
```

Cada documento possui um único PDF regular nesse layout. Não há cópias,
hardlinks ou aliases: o inventário rejeita mais de um caminho para o mesmo
SHA-256. Todos os artefatos e o único manifesto do documento ficam no diretório
irmão com o mesmo nome do PDF.

## Imagem MinerU

`infra/mineru/Dockerfile` gera uma imagem autocontida para Pods: MinerU,
dependências e modelos `pipeline` são instalados durante o build. A inicialização
revalida as dependências com `uv` e então executa `mineru-router`. O Volume
Disk é usado somente para resultados completos em `/workspace/results`; não há
fluxo Serverless nesta arquitetura.

`infra/mineru/start.sh` também pode ser executado diretamente em um pod
preparado manualmente. Ele instala `uv`, `mineru[pipeline]` e `hf_transfer`,
garante os modelos `pipeline` no cache local, conta as GPUs visíveis e inicia um
worker local por GPU. O router fixa o teto em **1024 agregado por pod**; com 8
GPUs, anuncia 128 por GPU. A janela de processamento é 64 e a pressão real é
controlada pelo cliente:

Use `poe extract start URL --workers 16` para iniciar o cliente.

O script divide os threads de CPU entre as GPUs e mantém modelos, cache, venv e
temporários no container. Os resultados só ficam disponíveis após a persistência
atômica em `/workspace/results`.

## Arquitetura operacional

A arquitetura recomendada mantém apenas um coordenador e evita duas filas
concorrentes para o mesmo trabalho:

```text
corpus + manifestos JSON atômicos
        |
        v
poe extract (circuit breaker de admissão e retry)
        |
        +---- limite explícito por endpoint ---+
        |                                      |
        v                                      v
mineru-router A                        mineru-router B
  +-- worker GPU 0                       +-- worker GPU 0
  +-- worker GPU 1                       +-- worker GPU 1
        |                                      |
        +------- pacote atômico no Volume -------+
                           |
                           v
        /workspace/results/<router-task-id>/
```

- Cada serviço anuncia seu teto em `/health`; o cliente nunca administra a
  infraestrutura que hospeda o endpoint.
- `poe extract start URL --workers 16` define a capacidade inicial do cliente
  por endpoint. O autotune ajusta somente a admissão, exclusivamente pelo pages/min
  sustentado; o circuit breaker bloqueia novos POSTs após falhas, sem reduzir
  workers.
- A fila transitória usa `AnyIO MemoryObjectStream`; `CapacityLimiter` permite
  alterar a concorrência em runtime e `TaskGroup` garante a drenagem estruturada.
- O controlador compara janelas sustentadas de pages/min após o settling. Só
  aumenta em degraus quando o ganho sustentado é >=5%; CPU >=90% por três
  leituras apenas adia o aumento, e volta a liberá-lo abaixo de 85%. Se o
  throughput cair ou estabilizar, retorna ao último patamar eficiente. As
  métricas ficam no log, nos manifestos e em `reconciliation.csv`.
- `poe extract scale URL --workers N` redefine a capacidade inicial do
  endpoint sem reiniciar os trabalhos em voo.
- O cliente só mantém em memória os trabalhos em voo. Depois de concluída, a
  tarefa só libera a vaga quando o router confirma o pacote atômico no Volume;
  o manifesto registra o caminho e os hashes, sem baixar ZIPs no hot path.
- Cada manifesto guarda inventário SHA-256, conclusão, erro, retry, tentativas,
  endpoint e `task_id`. Não há PostgreSQL: manifestos JSON atômicos são o único
  estado durável; fila ativa e telemetria permanecem transitórias.
- A parada é drenante: bloqueia novos envios e espera os trabalhos em voo.

Celery e Redis não fazem parte desta arquitetura. Há um único coordenador, e a
fila durável pode ser reconstruída a partir dos manifestos; adicionar outra fila
não controla a memória consumida pelos workers GPU. Se futuramente houver
vários coordenadores independentes, execução distribuída tolerante a falhas ou
necessidade de retomada de jobs em voo, essa decisão deve ser reavaliada.
