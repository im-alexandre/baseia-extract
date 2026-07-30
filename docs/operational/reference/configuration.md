---
id: operational.reference.configuration
title: Referência de configuração
kind: reference
audience: operator
mode: all
stage: configuration
status: current
nav_order: 420
---

# Referência de configuração

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](../production/README.md) · [Referência](README.md) ·
[Documentação técnica](../../technical/README.md)

O projeto lê variáveis do processo. `.env` é a configuração de conveniência
usada pelas ferramentas do projeto e pelo Compose. Uma variável definida no
processo atual pode prevalecer conforme a ferramenta que iniciar o comando.

Use [.env.example](../../../.env.example) como referência executável. Seus
segredos e endpoints são apenas defaults de desenvolvimento.

## Configuração da coleção

Uma coleção nova grava `baseia.collection.yaml` na raiz informada e usa
`.baseia/` como `state_dir`. O YAML contém:

- identidade, modo, escopo de recursos, topologia e etapa-alvo;
- uma ou mais fontes físicas e seus prefixos lógicos;
- nome/versão da estratégia;
- URLs de serviço, buckets e nomes das variáveis de credencial.

Valores de senha, token, access key e secret key não entram no YAML.

| Variável | Default | Papel |
| --- | --- | --- |
| `BASEIA_COLLECTION` | vazio | seleciona coleção sem alterar o registro |
| `BASEIA_COLLECTIONS_DIR` | data dir do usuário | sobrescreve o registro global |
| `BASEIA_COLLECTION_CONFIG` | injetada | path do YAML usado pelo worker |
| `BASEIA_CONTEXT_ID` | injetada | isola estado transitório de extração |
| `BASEIA_DOCUMENT_SOURCE_ROOTS` | injetada | lista JSON das fontes da coleção |

Use `poe collection configure` para alterar o contrato persistido. Variáveis
do processo continuam úteis para defaults e para valores secretos.

## Dados locais e compatibilidade

| Variável | Default | Papel |
| --- | --- | --- |
| `BASEIA_DATA_DIR` | `data` | estado do contexto; workers de coleção recebem `<raiz>/.baseia` |
| `BASEIA_DOCUMENT_STORE_DIR` | `data/documents` | fonte do fluxo local legado |
| `EXTRACTION_OUTPUT_DIR` | `data/extraction` | registros operacionais do extract |
| `BASEIA_BIND_HOST` | `127.0.0.1` | interface usada nas portas publicadas pelo Compose |

## MinerU e extract

| Variável | Default | Papel |
| --- | --- | --- |
| `MINERU_VERSION` | `3.4.4` | versão compatível com o patch |
| `MINERU_API_URL` | `http://127.0.0.1:8000` | URL usada quando nenhuma é informada |
| `MINERU_API_URLS` | vazio | lista separada por vírgula/espaço usada ao criar coleção |
| `MINERU_CONCURRENCY_PER_ENDPOINT` | `3` | capacidade inicial por endpoint |
| `MINERU_RETRIES` | `2` | retries do cliente |
| `MINERU_BACKEND` | `pipeline` | backend solicitado ao MinerU |
| `MINERU_OVERWRITE` | `false` | permite refazer resultados existentes |
| `MINERU_MATERIALIZE_RESULTS` | `true` | baixa intermediários S3 para render local |
| `MINERU_S3_DOWNLOAD_CONCURRENCY` | `4` | downloads simultâneos de materialização |
| `MINERU_SHARED_RESULTS` | `false` | modo de resultados compartilhados |

### Result store acessado pelo cliente

Use somente quando o MinerU persistir em um S3 diferente do canônico:

| Variável | Default | Papel |
| --- | --- | --- |
| `MINERU_RESULT_S3_ENDPOINT_URL` | S3 canônico | endpoint visto pelo cliente |
| `MINERU_RESULT_S3_BUCKET` | bucket retornado pela task | valida o bucket esperado |
| `MINERU_RESULT_S3_REGION` | região canônica | região do result store |
| `MINERU_RESULT_S3_ACCESS_KEY_ID` | credencial canônica se o endpoint for o mesmo | access key |
| `MINERU_RESULT_S3_SECRET_ACCESS_KEY` | credencial canônica se o endpoint for o mesmo | secret key |

No YAML, os campos `mineru_result_s3_*_env` armazenam apenas os nomes das duas
variáveis de credencial. O endpoint pode ser diferente do hostname interno
usado pelo container MinerU.

### Pool HTTP

| Variável | Default |
| --- | --- |
| `MINERU_HTTP_MAX_CONNECTIONS` | `256` |
| `MINERU_HTTP_MAX_KEEPALIVE_CONNECTIONS` | `128` |
| `MINERU_HTTP_KEEPALIVE_EXPIRY_SECONDS` | `30` |

### Timeouts

| Variável | Default, em segundos |
| --- | --- |
| `MINERU_HEALTH_TIMEOUT_SECONDS` | `30` |
| `MINERU_SUBMIT_TIMEOUT_SECONDS` | `300` |
| `MINERU_POLL_INTERVAL_SECONDS` | `1` |
| `MINERU_TASK_TIMEOUT_SECONDS` | `3600` |
| `MINERU_RESULT_TIMEOUT_SECONDS` | `3600` |
| `MINERU_ENDPOINT_WAIT_TIMEOUT_SECONDS` | `300` |

### Circuit breaker e autotune

| Variável | Default |
| --- | --- |
| `MINERU_CIRCUIT_FAILURE_THRESHOLD` | `3` |
| `MINERU_CIRCUIT_WINDOW_SECONDS` | `60` |
| `MINERU_CIRCUIT_COOLDOWN_SECONDS` | `30` |
| `MINERU_CIRCUIT_RECOVERY_SUCCESSES` | `2` |
| `MINERU_AUTOTUNE_SETTLING_SECONDS` | `30` |
| `MINERU_AUTOTUNE_WINDOW_SECONDS` | `120` |
| `MINERU_AUTOTUNE_MIN_SAMPLES` | `16` |
| `MINERU_AUTOTUNE_CPU_HIGH_PERCENT` | `90` |
| `MINERU_AUTOTUNE_CPU_HIGH_SAMPLES` | `3` |
| `MINERU_AUTOTUNE_CPU_RECOVERY_PERCENT` | `85` |

## Render

| Variável | Default | Papel |
| --- | --- | --- |
| `BASEIA_RENDER_PUBLISH_S3` | `false` | publica canônicos e conclui stage |
| `BASEIA_RENDER_PUBLISH_CONCURRENCY` | `4` | documentos publicados simultaneamente |
| `BASEIA_RENDER_S3_TRANSFER_CONCURRENCY` | `4` | transfers S3 por publicação |

`--workers 3` controla o processamento local do render. As duas concorrências
de publicação são limites diferentes.

A taxonomia desses limites ainda precisa ser unificada; consulte o
[TODO técnico de concorrência](../../technical/backlog/concurrency-model.md).

## Catálogo e PostgreSQL

| Variável | Default de desenvolvimento | Papel |
| --- | --- | --- |
| `BASEIA_DATABASE_URL` | PostgreSQL local | conexão usada pela Catalog API/Alembic |
| `BASEIA_CATALOG_API_URL` | `http://127.0.0.1:8088` | URL vista pelo cliente no host |
| `BASEIA_CATALOG_API_TOKEN` | vazio | bearer token |
| `BASEIA_REQUIRE_CATALOG_TOKEN` | `false` | falha no startup se não houver token |
| `CATALOG_API_HOST` | `127.0.0.1` | bind ao executar a API no host |
| `CATALOG_API_PORT` | `8088` | porta da API |
| `POSTGRES_DB` | `baseia` | banco local |
| `POSTGRES_USER` | `baseia` | usuário local |
| `POSTGRES_PASSWORD` | `baseia` | senha local insegura para produção |
| `POSTGRES_PORT` | `5432` | porta publicada |

## S3 compatível

| Variável | Default de desenvolvimento | Papel |
| --- | --- | --- |
| `BASEIA_S3_ENDPOINT_URL` | `http://127.0.0.1:8333` | endpoint visto pelo host |
| `BASEIA_S3_BUCKET` | `baseia` | bucket |
| `BASEIA_S3_MAX_CONCURRENCY` | `16` | transfers do artifact store |
| `AWS_ACCESS_KEY_ID` | `baseia` | credencial S3 |
| `AWS_SECRET_ACCESS_KEY` | `baseia-secret` | credencial S3 |
| `AWS_DEFAULT_REGION` | `us-east-1` | região |

Esses campos são o storage canônico usado por promoção, catálogo e publicação
do render. Não os confunda com `MINERU_RESULT_S3_*` quando a GPU usa outro
store.

Portas SeaweedFS:

| Variável | Default |
| --- | --- |
| `SEAWEED_S3_PORT` | `8333` |
| `SEAWEED_FILER_PORT` | `8888` |
| `SEAWEED_MASTER_PORT` | `9333` |

## Container MinerU

| Variável | Default | Papel |
| --- | --- | --- |
| `MINERU_RESULT_STORE` | `s3` no Compose | `s3` integrado; `filesystem` apenas sandbox |
| `MINERU_CATALOG_API_URL` | `http://catalog-api:8088` | catálogo visto pelo container |
| `MINERU_S3_ENDPOINT_URL` | `http://seaweedfs:8333` | S3 visto pelo container |
| `MINERU_PERSISTENCE_CONCURRENCY` | `4` | tasks publicadas simultaneamente |
| `MINERU_S3_UPLOAD_CONCURRENCY` | `8` | transfers S3 por publicação |
| `MINERU_ROUTER_MAX_CONCURRENT_REQUESTS` | `128` | limite agregado anunciado pelo router |
| `MINERU_MAX_UNPERSISTED_TASKS` | `256` | backlog local antes de backpressure |
| `MINERU_MIN_FREE_DISK_GIB` | `10` | mínimo livre absoluto |
| `MINERU_MIN_FREE_DISK_PERCENT` | `10` | mínimo livre percentual |
| `BASEIA_STAGE_LEASE_SECONDS` | `7200` | duração do lease |
| `MINERU_API_TASK_RETENTION_SECONDS` | `0` | retenção após commit durável |
| `MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS` | `60` | intervalo de limpeza |
| `MINERU_API_PORT` | `8000` | porta publicada |
| `MINERU_SHM_SIZE` | `8gb` | memória compartilhada do container |

Não reutilize `127.0.0.1` do host dentro do container: localhost sempre aponta
para o próprio container.

## Temporal

| Variável | Default |
| --- | --- |
| `TEMPORAL_POSTGRES_PASSWORD` | `temporal` |
| `TEMPORAL_VERSION` | `1.31.2` |
| `TEMPORAL_UI_VERSION` | `2.34.0` |
| `TEMPORAL_PORT` | `7233` |
| `TEMPORAL_UI_PORT` | `8080` |

Temporal está provisionado no perfil `production`, mas não participa do
pipeline atual.

## Auditoria

| Variável | Default |
| --- | --- |
| `AUDIT_TEXTLESS_PAGE_WARN_RATIO` | `0.5` |
| `AUDIT_MIN_MIDDLE_BYTES` | `1024` |
| `AUDIT_REVIEW_SAMPLE_SIZE` | `75` |

Anterior: [Comandos](commands.md)
Próximo: [Artefatos e saídas](artifacts.md)
Tutorial: [Usar serviços externos](../production/external-services.md)
Avançado: [Persistência e performance](../../technical/architecture/mineru-persistence.md)
