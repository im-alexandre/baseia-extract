# BaseIA Extract

Extração de PDFs com MinerU em pods transitórios do RunPod.

## Instalação

```powershell
uv sync
Copy-Item .env.example .env
```

Cada documento tem um manifesto JSON atômico em `data/mineru/manifests/`,
identificado pelo SHA-256. A fila, a ocupação e o inventário dos pods existem
somente durante a execução.

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
- saúde, capacidade, ocupação e ociosidade por pod;
- capacidade anunciada pela API e limite efetivo do cliente;
- fila interna anunciada pelo `/health` do MinerU.

O prazo de confirmação no Volume é no mínimo `MINERU_TASK_TIMEOUT_SECONDS`,
com cinco minutos adicionais para a cópia atômica; o padrão de
`MINERU_RESULT_TIMEOUT_SECONDS` é 3600 segundos. Um timeout mantém o `task_id`
no manifesto para retomada, sem novo envio do PDF.

O terminal não imprime o nome de cada documento. Um log textual com snapshots
periódicos é gravado no diretório temporário mostrado no início.

Enquanto a extração estiver ativa, use outro terminal:

```powershell
poe extract status
poe extract log
poe extract add POD_ID [OUTRO_POD_ID...]
poe extract add https://POD_ID-8000.proxy.runpod.net
poe extract stop
```

`poe extract stop` encerra o despacho de documentos novos, espera os que estão
em voo (incluindo seus retries) e depois executa `runpodctl pod stop` em todos
os pods gerenciados. Pods nunca são deletados.

`poe render` pode rodar depois ou em paralelo com a extração. Ele percorre o
inventário, processa somente documentos cujo `middle.json` já está disponível
e gera:

```text
data/ir/<document_id>/document_ir.json
data/structure/<document_id>/structure.json
data/structure/<document_id>/document.md
data/structure/<document_id>/render.json
data/structure/render_summary.json
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

Os artefatos continuam em:

```text
data/mineru/documents/<document_id>/
data/mineru/runs.csv
data/mineru/errors.csv
data/mineru/summary.json
data/mineru/pods.json
data/mineru/manifests/<sha256[:2]>/<sha256>.json
data/mineru/reconciliation.csv
```

## Pods e capacidade

No início, o coordenador reconcilia `runpodctl pod list --all`:

1. adota pods `RUNNING` com `RUNPOD_NAME_PREFIX`;
2. se faltar capacidade, inicia pods `STOPPED` do mesmo prefixo;
3. só então cria a quantidade restante;
4. começa a extrair assim que o primeiro `/health` responde;
5. incorpora pods adicionais em runtime.

Enquanto `RUNPOD_NETWORK_VOLUME_ID` estiver definido, todo pod novo usa o
Network Volume compartilhado em `/workspace`. Ele deve permanecer configurado
até que todos os pacotes da rodada tenham sido baixados e reconciliados. Quando
essa variável estiver vazia, novos pods recebem um **Volume Disk de 100 GB**
(configurável por `RUNPOD_VOLUME_DISK_GB`) em `/workspace`. Somente resultados
completos são gravados em `/workspace/results`; modelos, caches, ambiente Python
e temporários ficam no disco efêmero do container. O Volume Disk persiste entre
`stop` e `start` enquanto o pod não for deletado.

A seleção usa o perfil `RUNPOD_HARDWARE_PROFILE=mineru-budget-24`, que prioriza
GPUs com boa relação CPU/GPU. Além do mínimo de VRAM e
CUDA, todo pod criado precisa atender a `RUNPOD_MIN_VCPU_COUNT`,
`RUNPOD_MIN_MEMORY_GB` e `RUNPOD_MAX_COST_PER_HOUR`. Uma máquina fora desses
limites é descartada e o próximo tipo disponível é tentado. A configuração-alvo
é **4 pods × 8 GPUs**.

Todos os pods anunciam o guardrail de **1024 requisições agregadas por pod** em
`MINERU_API_MAX_CONCURRENT_REQUESTS`. Em 8 GPUs, isso equivale a **128 por
GPU**. O cliente começa com `--workers 16` por pod; depois, o autotune altera a
admissão exclusivamente pelo pages/min sustentado. Para pods existentes ou
adicionados manualmente, o cliente respeita a capacidade anunciada pelo
`/health`.

## Imagem MinerU

`mineru-server/Dockerfile` gera uma imagem autocontida para Pods: MinerU,
dependências e modelos `pipeline` são instalados durante o build. A inicialização
revalida as dependências com `uv` e então executa `mineru-router`. O Volume
Disk é usado somente para resultados completos em `/workspace/results`; não há
fluxo Serverless nesta arquitetura.

`mineru-server/start.sh` também pode ser executado diretamente em um pod
preparado manualmente. Ele instala `uv`, `mineru[pipeline]` e `hf_transfer`,
garante os modelos `pipeline` no cache local, conta as GPUs visíveis e inicia um
worker local por GPU. O router fixa o teto em **1024 agregado por pod**; com 8
GPUs, anuncia 128 por GPU. A janela de processamento é 64 e a pressão real é
controlada pelo cliente:

```powershell
poe ingest POD_ID --workers 16
```

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
poe ingest (circuit breaker de admissão e retry)
        |
        +------ limite explícito por pod ------+
        |                                      |
        v                                      v
mineru-router Pod A                    mineru-router Pod B
  +-- worker GPU 0                       +-- worker GPU 0
  +-- worker GPU 1                       +-- worker GPU 1
        |                                      |
        +------- pacote atômico no Volume -------+
                           |
                           v
        /workspace/results/<router-task-id>/
```

- O `mineru-router` cria um worker por GPU visível e distribui apenas dentro do
  próprio pod. Seu teto é 1024 agregado por pod (128/GPU na configuração de
  oito GPUs) e a janela é 64.
- `poe ingest POD_ID --workers 16` define a capacidade inicial do cliente por
  pod. O autotune ajusta somente a admissão, exclusivamente pelo pages/min
  sustentado; o circuit breaker bloqueia novos POSTs após falhas, sem reduzir
  workers.
- A fila transitória usa `AnyIO MemoryObjectStream`; `CapacityLimiter` permite
  alterar a concorrência em runtime e `TaskGroup` garante a drenagem estruturada.
- O controlador compara janelas sustentadas de pages/min após o settling. Só
  aumenta em degraus quando o ganho sustentado é >=5%; CPU >=90% por três
  leituras apenas adia o aumento, e volta a liberá-lo abaixo de 85%. Se o
  throughput cair ou estabilizar, retorna ao último patamar eficiente. As
  métricas ficam no log, nos manifestos e em `reconciliation.csv`.
- Repetir `poe ingest POD_ID --workers N` durante a execução redefine a
  capacidade inicial do pod sem reiniciar os trabalhos em voo.
- O cliente só mantém em memória os trabalhos em voo. Depois de concluída, a
  tarefa só libera a vaga quando o router confirma o pacote atômico no Volume;
  o manifesto registra o caminho e os hashes, sem baixar ZIPs no hot path.
- Cada manifesto guarda inventário SHA-256, conclusão, erro, retry, tentativas,
  endpoint e `task_id`. Não há PostgreSQL: manifestos JSON atômicos são o único
  estado durável; fila ativa, telemetria e pods permanecem transitórios.
- A parada é drenante: bloqueia novos envios, espera os trabalhos em voo e
  então para os pods gerenciados.

Celery e Redis não fazem parte desta arquitetura. Há um único coordenador, e a
fila durável pode ser reconstruída a partir dos manifestos; adicionar outra fila
não controla a memória consumida pelos workers GPU. Se futuramente houver
vários coordenadores independentes, execução distribuída tolerante a falhas ou
necessidade de retomada de jobs em voo, essa decisão deve ser reavaliada.

No template RunPod:

- exponha `8000/http`;
- mantenha `RUNPOD_NETWORK_VOLUME_ID` durante a rodada atual; depois, deixe o
  criador automático anexar o Volume Disk de 100 GB em `/workspace`;
- deixe Docker Entrypoint e Docker Start Command vazios;
- use a imagem publicada quando MinerU ou seus modelos forem atualizados.
