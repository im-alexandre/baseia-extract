---
id: technical.concepts.ingestion
title: Ingestão e retrieval
kind: concept
audience: maintainer
mode: all
stage: ingest
status: current
nav_order: 575
---

# Ingestão e retrieval

[Documentação](../../README.md) · [Documentação técnica](../README.md) · [Pipeline](pipeline.md) · [Artefatos](artifacts.md)

## Contrato e política

`poe ingest prepare` exige uma política YAML. Ela define o perfil, o splitter,
as ações para todos os papéis semânticos, modelo/dimensões de embedding e a
coleção Qdrant. A política é validada estritamente: figuras, tabelas e equações
usam placeholders; cada papel deve estar declarado. A resolução segue
`--policy`, `strategy.ingest_policy` no `baseia.collection.yaml`,
`.baseia/embedding.yaml` sob `--path` e, por fim,
`BASEIA_INGEST_POLICY`.

O estágio lê `document_ir.json`, `structure.json`, `metadata.json`,
`document.md` e `render.json`, valida a estrutura e registra seus hashes. A
saída local é `canonical/chunks/<perfil>.jsonl` e
`canonical/ingest/<perfil>.json`; uma entrada atual é reutilizada quando
política, versões e hashes não mudaram.

## Chunking hierárquico

Os chunks são construídos a partir da `DocumentStructure`, não reconstruindo a estrutura a partir do Markdown. O fluxo segue seções, `heading_path`, ordem de leitura, blocos e páginas; depois usa `RecursiveCharacterTextSplitter.from_tiktoken_encoder` com `cl100k_base`, tamanho e sobreposição da política. O texto de embedding pode receber prefixo contextual de título e headings.

Cada chunk contém IDs de documento, revisão, seção e blocos, páginas, papéis,
hashes, metadados bibliográficos compactos e o hash da política. O ID do chunk
é UUIDv5 determinístico da revisão, política, índice e hash do texto; o pai é
determinístico por seção. Texto não embedável pode ir para payload ou ser
excluído. Assets de figuras, tabelas e equações preservam metadados, HTML ou
LaTeX e, se habilitado, base64; placeholders e legendas mantêm o contexto
textual sem embutir o conteúdo interno da tabela.

Autores pessoais e corporativos confirmados pelo render seguem no payload
bibliográfico compacto. Revisões ainda obrigatórias permanecem observáveis no
manifesto de ingestão; a confirmação em `metadata-overrides.yaml` remove a
pendência sem apagar sua proveniência manual.

O payload também leva a object key determinística do PDF original e, quando o
bucket está configurado, a URI `s3://` que será válida depois da promoção. A
URI pode, portanto, ser calculada antes do upload sem afirmar que o objeto já
existe.

## Apply e Qdrant

`poe ingest apply` primeiro faz o mesmo preparo e então usa `OpenAIEmbeddings` contra OpenRouter. O default da política é `openai/text-embedding-3-small`, com 1536 dimensões. Um embedding de prova é validado antes de criar ou reutilizar a coleção Qdrant, que deve usar vetor denso sem nome, dimensão idêntica e distância cosine.

O writer usa `QdrantVectorStore` para adicionar textos com os IDs determinísticos. Antes do upsert, consulta os pontos do mesmo `document_id` e perfil; depois remove os IDs que ficaram obsoletos quando `qdrant.replace_documents=true`. Índices de payload para documento, coleção e política apoiam essa reconciliação. O manifest de ingestão só é marcado como `complete` após o upsert e a limpeza.

Uma política representa um contrato vetorial. Perfis com modelo, dimensão ou semântica incompatíveis devem usar coleções físicas Qdrant distintas, em vez de misturar pontos em uma coleção existente.

Anterior: [Artefatos e layout](artifacts.md)
Próximo: [Guia de desenvolvimento](../development/guide.md)
Operação relacionada: [Referência de comandos](../../operational/reference/commands.md)
