# AGENTS.md

## Papel deste arquivo

Este arquivo reúne regras estáveis para trabalhar no repositório. Detalhes
operacionais, comandos, layouts e decisões que podem evoluir permanecem na
documentação canônica; não os replique aqui.

Antes de alterar uma área, leia:

1. [estrutura do repositório](docs/technical/repository-structure.md);
2. [visão geral da arquitetura](docs/technical/architecture/overview.md);
3. o conceito, adaptador ou modo operacional afetado;
4. a task correspondente em `pyproject.toml` e sua implementação real.

Os portais de entrada são:

- [documentação operacional](docs/operational/README.md), para uso do
  framework;
- [documentação técnica](docs/technical/README.md), para arquitetura e
  desenvolvimento;
- [referência de comandos](docs/operational/reference/commands.md), para a
  interface CLI vigente;
- [guia de desenvolvimento](docs/technical/development/guide.md), para o fluxo
  de manutenção.

Em caso de divergência, confirme o comportamento no código e informe o drift.
Não transforme uma descrição histórica ou um recurso marcado como futuro em
contrato vigente.

## Modos de execução

Identifique o modo afetado antes de modificar ou executar o pipeline:

- **local:** prioriza `uv`, Poe, filesystem e inspeção artesanal. Inventário,
  amostragem, render e auditoria não devem exigir serviços que não sejam
  inerentes à etapa. A extração pode usar um MinerU local, em container ou
  externo;
- **desenvolvimento catalogado:** usa Catalog API, PostgreSQL e storage
  compatível com S3 para preservar snapshots, runs, leases e artefatos de
  experimentação;
- **produção:** começa com inventário, snapshots, runs e manifestos novos.
  Reaplica a estratégia aprovada, sem promover automaticamente estado
  operacional de desenvolvimento.

Nunca promova para produção task IDs, tentativas, leases, logs, URLs
temporárias, manifests experimentais ou histórico de runs de desenvolvimento.
`poe bootstrap` continua sendo compatibilidade da consolidação legada.
`poe promote-s3` aceita inventários arbitrários validados, mas o fluxo
preferencial de uma coleção registrada é `poe init` seguido de
`poe pipeline --through promote`.

Temporal está provisionado como infraestrutura futura, mas não é o
orquestrador ativo do pipeline. Hoje, as tasks Poe e o CLI coordenam os fluxos.
O outbox transacional também não deve ser tratado como fila ativa enquanto não
houver dispatcher implementado.

## Invariantes do domínio

Preserve estes contratos:

- a identidade de um documento é formada pela coleção e pelo caminho relativo;
- SHA-256 identifica conteúdo e integridade, não a identidade lógica;
- dois caminhos distintos representam documentos distintos, mesmo que tenham
  bytes idênticos; não crie aliases nem mescle registros por hash;
- caminhos locais absolutos não fazem parte do contrato publicado;
- um snapshot ativo congela a composição exata da coleção; artefatos
  posteriores não alteram snapshots históricos;
- o PDF original permanece no seu caminho e os artefatos ficam no diretório
  irmão do documento, conforme o
  [contrato de artefatos](docs/technical/concepts/artifacts.md);
- `manifest.json` é o índice materializado e o commit marker do documento:
  publique payloads primeiro, valide tamanho e SHA-256, grave metadados e
  publique o manifesto por último;
- o render é o único produtor de `canonical/document.md`;
- o Markdown produzido pelo MinerU é intermediário e não deve ser preservado
  como Markdown canônico.

## Fronteiras entre componentes

Respeite a responsabilidade de cada camada:

- **PostgreSQL:** identidade, snapshots, estados, locks, leases e fencing; não
  armazena o payload dos documentos;
- **Catalog API:** único writer dos metadados canônicos. Clientes, workers e
  MinerU não escrevem diretamente no banco;
- **storage S3:** payloads e snapshots duráveis; não é fila, lock, mecanismo de
  fencing nem fonte de exclusão mútua;
- **MinerU:** parsing e artefatos intermediários;
- **adapters BaseIA:** idempotência, catálogo, persistência S3, retries e
  reconciliação;
- **render:** IR, estrutura e artefatos finais canônicos; não decide identidade;
- **CLI/Poe:** coordenação atual. Estado local do CLI não se torna
  automaticamente estado canônico de produção.

Não use ETag como se fosse MD5. Não use diretórios temporários como contrato
entre serviços: troque referências duráveis e inequívocas a artefatos.

## Persistência, idempotência e concorrência

Operações catalogadas devem seguir os contratos descritos em
[arquitetura do catálogo](docs/technical/architecture/catalog.md):

- derive a chave de uma etapa a partir da revisão, estágio,
  processador/versão, hash da configuração e hashes das entradas;
- implemente `get-or-create` com unicidade no banco e lock transacional;
- proteja leases com owner e attempt/fencing token;
- aceite heartbeat, conclusão e falha somente do owner/attempt vigente;
- mantenha transições idempotentes e não regressivas;
- só marque uma etapa como concluída depois de verificar uploads;
- grave artefatos e estado concluído na mesma transação de catálogo.

Não crie fila, retry, agendamento, distribuição ou controle de concorrência
manual quando uma biblioteca madura ou um componente existente resolver o
problema. Inspecione primeiro as dependências e APIs já adotadas.

`workers`, admissão HTTP, endpoints MinerU, GPUs, pools de conexão,
transferências S3 e publicação do render são capacidades diferentes. Não trate
esses controles como um único número nem faça ajustes oportunistas para
“corrigir” sua semântica. Consulte o
[backlog do modelo de concorrência](docs/technical/backlog/concurrency-model.md)
quando a mudança tocar esse tema.

Uma conexão HTTP perdida não prova que uma extração falhou. Consulte o estado
persistido e use o fluxo de recuperação antes de reenviar trabalho; faça
inspeção sem `--apply` antes de aplicar recuperação.

## Pontos de entrada

Localize a task em `pyproject.toml` e preserve o encadeamento existente:

- inventário e amostragem: `src/baseia_extract/inventory.py`;
- contexto, registro e execução de coleções:
  `src/baseia_extract/collection.py` e
  `src/baseia_extract/collection_worker.py`;
- extração: `src/baseia_extract/tasks.py` →
  `src/baseia_extract/extract_control.py` →
  `src/baseia_extract/mineru.py`;
- recuperação: `src/baseia_extract/recover.py`;
- render: `src/baseia_extract/render.py` e
  `src/baseia_extract/render_publish.py`;
- auditoria: `src/baseia_extract/audit.py`;
- bootstrap local: `src/baseia_extract/bootstrap.py`;
- promoção S3: `src/baseia_extract/bootstrap_s3.py`;
- catálogo: `src/baseia_extract/catalog/`;
- schema do catálogo: `infra/catalog/migrations/`.

Use `uv run poe ...` como interface preferencial. Antes de alterar parâmetros
ou exemplos, confira `uv run poe --help <task>`.

## Coleções e dados persistentes

Fontes registradas, `data/documents` legado e os volumes de PostgreSQL/S3
podem conter estado valioso.
Não faça operações destrutivas, migrações em massa, quarentena, bootstrap,
promoção ou render de toda a coleção sem que isso esteja claramente no escopo
autorizado.

Antes de uma operação sobre a coleção:

- resolva e valide os caminhos exatos;
- use modo de plano ou inspeção quando disponível;
- preserve journal, lock e quarentena usados para recuperação;
- diferencie PDFs do corpus de referências técnicas;
- confirme contagens, chaves, tamanhos e SHA-256 antes de mudar a autoridade do
  inventário local para um snapshot S3.

Coleções novas permanecem fora do worktree. Não copie PDFs para o repositório
como etapa de `init`, `sample`, `pipeline` ou `quick`. Preserve
`baseia.collection.yaml` e `.baseia/` na raiz da coleção e mantenha no registro
global apenas o nome e o path dessa configuração. O YAML referencia nomes de
variáveis de credencial; nunca grave os valores dos segredos nele.

`docker compose down` e `docker compose down --volumes` têm efeitos diferentes.
Não remova volumes persistentes como efeito colateral de um teste.

## Alterações no MinerU

O patch de persistência existe apenas como integração mínima com o runtime
MinerU. Antes de alterá-lo:

1. inspecione a versão instalada, o wheel/runtime e os patches atuais;
2. consulte a documentação oficial e procure um hook público equivalente;
3. mantenha a alteração pequena, versionada e com falha explícita para versões
   desconhecidas;
4. valide build, inicialização, GPU e um PDF representativo antes de declarar
   compatibilidade.

Não mova identidade, idempotência, regras de catálogo ou outros contratos
canônicos para o monkey patch. Remova o patch quando o runtime oferecer uma
extensão pública adequada. Consulte
[persistência do MinerU](docs/technical/architecture/mineru-persistence.md).

## Validação e testes

Valide na proporção do risco. O conjunto básico é:

```powershell
uv lock --check
uv run python -m compileall -q src infra
docker compose --profile catalog config
git diff --check
```

Execute também a ajuda da task e a validação dos perfis Compose afetados.
Smoke tests reais são preferíveis quando o ambiente existe, a operação é
segura e está autorizada.

Não crie testes unitários artificiais para código de infraestrutura,
provisionamento ou orquestração, especialmente testes baseados em mocks de
CLI, processos, pods, GPUs ou serviços externos.

Para esse tipo de alteração, prefira:

- validação estática e de sintaxe;
- inspeção dos comandos gerados;
- smoke tests operacionais quando forem seguros e autorizados;
- testes de integração somente quando houver ambiente apropriado e solicitação
  explícita.

Não adicione uma suíte unitária apenas para simular `runpodctl`, criação de
processos em background ou disponibilidade de pods.

## Documentação viva

A documentação só pode ser atualizada quando o usuário solicitar diretamente
sua atualização ou alteração.

Não modifique `README.md`, `SOUL.md` nem arquivos em `docs/` como efeito
colateral de mudanças em código, configuração, infraestrutura, comandos ou
comportamento. Quando uma alteração não autorizada na documentação puder
causar drift, registre a divergência no relatório final e solicite autorização
explícita para corrigi-la.

Quando o usuário solicitar uma mudança documental, siga
[manutenção da documentação](docs/technical/development/documentation.md):

- preserve front matter, IDs semânticos e um único H1;
- mantenha headings hierárquicos, links relativos e navegação entre páginas;
- confira tasks, defaults, endpoints e healthchecks contra a implementação;
- marque recursos futuros como futuros;
- valide links locais e unicidade dos IDs;
- preserve `SOUL.md` integralmente, sem normalização editorial incidental.
