# BaseIA Extract

Framework para inventariar, diagnosticar, extrair, renderizar e preparar
coleções documentais. O BaseIA pode ser usado em uma estação de trabalho, em
desenvolvimento com catálogo ou em uma topologia distribuída de produção.

## Documentação

A documentação possui duas entradas:

- [Usar o BaseIA](docs/operational/README.md) — instalação, Quick Start,
  tutoriais por ambiente e referência de comandos;
- [Desenvolver o framework](docs/technical/README.md) — estrutura do
  repositório, arquitetura, modelos e manutenção.

O [índice geral](docs/README.md) conecta os dois percursos. A intenção e os
limites de produto permanecem preservados integralmente em
[SOUL.md](SOUL.md).

## Modos de execução

| Modo | Objetivo | Serviços necessários |
| --- | --- | --- |
| Local | inventariar, amostrar, experimentar e inspecionar | nenhum para inventário e amostragem; extração requer um backend MinerU |
| Dev catalogado | persistir inventário, runs e artefatos | PostgreSQL, catálogo e S3 compatível |
| Produção | executar a estratégia validada com registros limpos | catálogo e S3; serviços MinerU podem estar em outros hosts |

Comece pelo [Quick Start local](docs/operational/local/quickstart.md).

## Primeiro uso

Os documentos permanecem no diretório informado. O BaseIA grava a
configuração `baseia.collection.yaml` e o estado `.baseia/` junto da coleção,
sem copiar PDFs para o repositório:

```powershell
uv sync
uv run poe init "D:/colecoes/meus-pdfs" --name "Meus PDFs"
uv run poe collection ls
uv run poe sample --collection "Meus PDFs" --size 3
uv run poe pipeline --collection "Meus PDFs" --through render --sample `
    --api-url "http://127.0.0.1:8000"
```

Para incorporar rapidamente um paper e levá-lo à mesma etapa da coleção:

```powershell
uv run poe quick "D:/entrada/novo-paper.pdf" `
    --collection "Meus PDFs"
```

`collection`, `init`, `sample`, `pipeline` e `quick` são os comandos
preferenciais para coleções registradas. As tasks de baixo nível permanecem
disponíveis para manutenção do layout legado e experimentação direta.

## Layout documental

Cada PDF possui um diretório irmão. O Markdown produzido pelo MinerU é
intermediário; somente o Markdown produzido pelo render é canônico.

```text
<raiz-da-coleção>/
├── baseia.collection.yaml
├── .baseia/
│   ├── inventory/
│   ├── audit/
│   ├── extraction/
│   └── pipeline/
├── <subdiretórios>/arquivo.pdf
└── <subdiretórios>/arquivo/
    ├── manifest.json
    ├── intermediate/
    │   └── mineru/
    └── canonical/
        ├── document_ir.json
        ├── structure.json
        ├── document.md
        └── render.json
```

Identidade é coleção + caminho relativo. SHA-256 identifica o conteúdo de uma
revisão e comprova sua integridade; caminhos diferentes continuam sendo
documentos diferentes.
