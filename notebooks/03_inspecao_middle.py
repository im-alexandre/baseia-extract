# %% [markdown]
# # 03 — Inspeção estrutural das saídas `middle.json`
#
# Este notebook inspeciona a representação intermediária produzida pelo MinerU.
#
# Objetivos:
#
# - localizar os arquivos `*_middle.json` da amostra smoke;
# - validar a estrutura geral dos documentos;
# - inventariar tipos de blocos, linhas e spans;
# - inspecionar títulos, tabelas, figuras e fórmulas;
# - analisar cabeçalhos, rodapés e outros blocos descartados;
# - identificar continuidade de conteúdo entre páginas;
# - gerar tabelas consolidadas para orientar a construção do IR canônico.
#
# Nenhuma normalização semântica será aplicada nesta etapa.

# %%
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from IPython.display import Markdown, display

pd.set_option("display.max_columns", 100)
pd.set_option("display.max_colwidth", 160)
pd.set_option("display.width", 220)

# %% [markdown]
# ## 1. Caminhos do projeto

# %%
PROJECT_ROOT = Path.cwd()

if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent


SMOKE_MANIFEST = PROJECT_ROOT / "data" / "samples" / "benchmark_smoke_sample.csv"

MINERU_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mineru"

REPORTS_ROOT = PROJECT_ROOT / "data" / "reports" / "middle_inspection"

REPORTS_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


PROJECT_ROOT, SMOKE_MANIFEST, MINERU_OUTPUT_ROOT, REPORTS_ROOT

# %% [markdown]
# ## 2. Carregamento da amostra smoke

# %%
if not SMOKE_MANIFEST.exists():
    raise FileNotFoundError(f"Manifesto smoke não encontrado: {SMOKE_MANIFEST}")


smoke_sample = pd.read_csv(SMOKE_MANIFEST)

required_columns = {
    "filename",
    "path",
}

missing_columns = required_columns.difference(smoke_sample.columns)

if missing_columns:
    raise ValueError(f"Colunas ausentes no manifesto smoke: {sorted(missing_columns)}")


smoke_sample

# %% [markdown]
# ## 3. Localização dos arquivos `middle.json`
#
# O MinerU normalmente cria um diretório por documento. A busca abaixo usa
# primeiro o nome base do PDF e, em seguida, faz uma busca global pelo sufixo
# `_middle.json`.


# %%
def normalize_stem(value: str | Path) -> str:
    return Path(str(value)).stem.casefold()


def discover_middle_files(
    output_root: Path,
) -> list[Path]:
    if not output_root.exists():
        return []

    return sorted(path for path in output_root.rglob("*_middle.json") if path.is_file())


all_middle_files = discover_middle_files(MINERU_OUTPUT_ROOT)

len(all_middle_files)

# %%
middle_files_by_stem: dict[str, list[Path]] = {}

for middle_path in all_middle_files:
    filename = middle_path.name

    if filename.endswith("_middle.json"):
        document_stem = filename.removesuffix("_middle.json")
    else:
        document_stem = middle_path.stem

    middle_files_by_stem.setdefault(
        document_stem.casefold(),
        [],
    ).append(middle_path)


def match_middle_file(
    filename: str,
    source_path: str | Path,
) -> tuple[Path | None, str]:
    candidate_stems = {
        normalize_stem(filename),
        normalize_stem(source_path),
    }

    exact_matches: list[Path] = []

    for candidate_stem in candidate_stems:
        exact_matches.extend(
            middle_files_by_stem.get(
                candidate_stem,
                [],
            )
        )

    exact_matches = sorted(set(exact_matches))

    if len(exact_matches) == 1:
        return exact_matches[0], "exact"

    if len(exact_matches) > 1:
        return exact_matches[0], "multiple_exact"

    fuzzy_matches = [
        path
        for path in all_middle_files
        if any(
            candidate_stem and candidate_stem in path.name.casefold()
            for candidate_stem in candidate_stems
        )
    ]

    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0], "fuzzy"

    if len(fuzzy_matches) > 1:
        return fuzzy_matches[0], "multiple_fuzzy"

    return None, "not_found"


middle_manifest_rows: list[dict[str, Any]] = []

for row in smoke_sample.itertuples(index=False):
    middle_path, match_method = match_middle_file(
        filename=str(row.filename),
        source_path=str(row.path),
    )

    middle_manifest_rows.append(
        {
            "filename": row.filename,
            "source_path": row.path,
            "middle_path": (str(middle_path) if middle_path is not None else None),
            "middle_exists": (middle_path is not None and middle_path.exists()),
            "match_method": match_method,
        }
    )


middle_manifest = pd.DataFrame(middle_manifest_rows)

middle_manifest

# %%
missing_middle = middle_manifest[~middle_manifest["middle_exists"]].copy()

if not missing_middle.empty:
    display(Markdown("### Arquivos `middle.json` não encontrados"))
    display(missing_middle)
else:
    display(
        Markdown("Todos os arquivos `middle.json` da amostra smoke foram encontrados.")
    )

# %% [markdown]
# ## 4. Leitura e validação básica dos JSONs


# %%
def load_json(
    path: Path,
) -> Any:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def validate_middle_document(
    data: Any,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["A raiz do middle.json não é um objeto JSON."]

    pdf_info = data.get("pdf_info")

    if not isinstance(pdf_info, list):
        errors.append("`pdf_info` não existe ou não é uma lista.")
        return errors

    for page_index, page in enumerate(pdf_info):
        if not isinstance(page, dict):
            errors.append(f"Página {page_index}: valor não é objeto.")
            continue

        if "page_idx" not in page:
            errors.append(f"Página {page_index}: `page_idx` ausente.")

        for field in (
            "preproc_blocks",
            "para_blocks",
            "discarded_blocks",
        ):
            value = page.get(field)

            if value is not None and not isinstance(
                value,
                list,
            ):
                errors.append(f"Página {page_index}: `{field}` não é lista.")

    return errors


loaded_documents: dict[str, dict[str, Any]] = {}
validation_rows: list[dict[str, Any]] = []

for row in middle_manifest.itertuples(index=False):
    if not row.middle_exists:
        validation_rows.append(
            {
                "filename": row.filename,
                "middle_path": row.middle_path,
                "loaded": False,
                "valid": False,
                "page_count": None,
                "error_count": 1,
                "errors": "Arquivo não encontrado.",
            }
        )
        continue

    middle_path = Path(row.middle_path)

    try:
        data = load_json(middle_path)
        errors = validate_middle_document(data)

        document_id = normalize_stem(row.filename)

        loaded_documents[document_id] = {
            "filename": row.filename,
            "source_path": row.source_path,
            "middle_path": middle_path,
            "data": data,
        }

        validation_rows.append(
            {
                "filename": row.filename,
                "middle_path": str(middle_path),
                "loaded": True,
                "valid": not errors,
                "page_count": len(
                    data.get(
                        "pdf_info",
                        [],
                    )
                ),
                "error_count": len(errors),
                "errors": " | ".join(errors),
            }
        )

    except Exception as exc:
        validation_rows.append(
            {
                "filename": row.filename,
                "middle_path": str(middle_path),
                "loaded": False,
                "valid": False,
                "page_count": None,
                "error_count": 1,
                "errors": (f"{type(exc).__name__}: {exc}"),
            }
        )


validation_df = pd.DataFrame(validation_rows)

validation_df

# %%
if not loaded_documents:
    raise RuntimeError("Nenhum middle.json pôde ser carregado.")

# %% [markdown]
# ## 5. Funções auxiliares de navegação


# %%
def iter_pages(
    document: dict[str, Any],
) -> Iterable[tuple[int, dict[str, Any]]]:
    pdf_info = document.get(
        "pdf_info",
        [],
    )

    for fallback_index, page in enumerate(pdf_info):
        page_index = page.get(
            "page_idx",
            fallback_index,
        )

        yield int(page_index), page


def iter_blocks(
    document: dict[str, Any],
    field: str,
) -> Iterable[tuple[int, int, dict[str, Any]]]:
    for page_index, page in iter_pages(document):
        blocks = (
            page.get(
                field,
                [],
            )
            or []
        )

        for fallback_index, block in enumerate(blocks):
            block_index = block.get(
                "index",
                fallback_index,
            )

            yield (
                page_index,
                int(block_index),
                block,
            )


def iter_lines(
    block: dict[str, Any],
) -> Iterable[tuple[int, dict[str, Any]]]:
    lines = (
        block.get(
            "lines",
            [],
        )
        or []
    )

    for line_index, line in enumerate(lines):
        yield line_index, line


def iter_spans(
    line: dict[str, Any],
) -> Iterable[tuple[int, dict[str, Any]]]:
    spans = (
        line.get(
            "spans",
            [],
        )
        or []
    )

    for span_index, span in enumerate(spans):
        yield span_index, span


def extract_text_from_span(
    span: dict[str, Any],
) -> str:
    for key in (
        "content",
        "text",
        "latex",
        "html",
    ):
        value = span.get(key)

        if value not in (
            None,
            "",
        ):
            return str(value)

    return ""


def extract_text_from_line(
    line: dict[str, Any],
) -> str:
    texts = [extract_text_from_span(span) for _, span in iter_spans(line)]

    return " ".join(text for text in texts if text).strip()


def extract_text_from_block(
    block: dict[str, Any],
) -> str:
    direct_candidates = (
        block.get("content"),
        block.get("text"),
        block.get("latex"),
        block.get("html"),
    )

    for candidate in direct_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    lines = [extract_text_from_line(line) for _, line in iter_lines(block)]

    return " ".join(line for line in lines if line).strip()


def bbox_metrics(
    bbox: Any,
) -> dict[str, float | None]:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return {
            "x0": None,
            "y0": None,
            "x1": None,
            "y1": None,
            "width": None,
            "height": None,
            "area": None,
        }

    try:
        x0, y0, x1, y1 = map(
            float,
            bbox,
        )
    except (
        TypeError,
        ValueError,
    ):
        return {
            "x0": None,
            "y0": None,
            "x1": None,
            "y1": None,
            "width": None,
            "height": None,
            "area": None,
        }

    width = max(
        0.0,
        x1 - x0,
    )
    height = max(
        0.0,
        y1 - y0,
    )

    return {
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "width": width,
        "height": height,
        "area": width * height,
    }


def truncate_text(
    value: Any,
    limit: int = 240,
) -> str:
    text = str(value or "").replace(
        "\n",
        " ",
    )

    text = " ".join(text.split())

    if len(text) <= limit:
        return text

    return text[: limit - 1] + "…"


# %% [markdown]
# ## 6. Tabela plana de blocos
#
# Cada linha representa um bloco do `middle.json`.
#
# São mantidas separadamente as três coleções principais:
#
# - `preproc_blocks`;
# - `para_blocks`;
# - `discarded_blocks`.

# %%
BLOCK_FIELDS = (
    "preproc_blocks",
    "para_blocks",
    "discarded_blocks",
)


block_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for (
            page_index,
            block_index,
            block,
        ) in iter_blocks(
            document,
            block_collection,
        ):
            bbox = bbox_metrics(block.get("bbox"))

            lines = (
                block.get(
                    "lines",
                    [],
                )
                or []
            )

            spans = [span for line in lines for _, span in iter_spans(line)]

            block_rows.append(
                {
                    "document_id": document_id,
                    "filename": document_record["filename"],
                    "middle_path": str(document_record["middle_path"]),
                    "block_collection": (block_collection),
                    "page_index": page_index,
                    "page_number": page_index + 1,
                    "block_index": block_index,
                    "block_type": block.get("type"),
                    "level": block.get("level"),
                    "score": block.get("score"),
                    "line_count": len(lines),
                    "span_count": len(spans),
                    "text": extract_text_from_block(block),
                    "text_length": len(extract_text_from_block(block)),
                    "has_bbox": (block.get("bbox") is not None),
                    "has_bbox_fs": (block.get("bbox_fs") is not None),
                    "lines_deleted": bool(
                        block.get(
                            "lines_deleted",
                            False,
                        )
                    ),
                    "has_blocks": bool(block.get("blocks")),
                    "has_image_path": bool(
                        block.get("image_path") or block.get("img_path")
                    ),
                    "has_html": bool(block.get("html")),
                    "has_latex": bool(block.get("latex")),
                    **bbox,
                }
            )


blocks_df = pd.DataFrame(block_rows)

blocks_df.shape

# %%
blocks_df.head(20)

# %% [markdown]
# ## 7. Inventário de tipos de bloco

# %%
block_type_counts = (
    blocks_df.groupby(
        [
            "block_collection",
            "block_type",
        ],
        dropna=False,
    )
    .size()
    .rename("count")
    .reset_index()
    .sort_values(
        [
            "block_collection",
            "count",
            "block_type",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )
    .reset_index(drop=True)
)

block_type_counts

# %%
block_type_by_document = blocks_df.pivot_table(
    index="filename",
    columns=[
        "block_collection",
        "block_type",
    ],
    values="block_index",
    aggfunc="count",
    fill_value=0,
).sort_index(axis=1)

block_type_by_document

# %% [markdown]
# ## 8. Estrutura de páginas e coleções de blocos

# %%
page_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    for page_index, page in iter_pages(document_record["data"]):
        page_size = page.get(
            "page_size",
            [],
        )

        page_width = (
            page_size[0]
            if isinstance(page_size, list) and len(page_size) >= 2
            else None
        )

        page_height = (
            page_size[1]
            if isinstance(page_size, list) and len(page_size) >= 2
            else None
        )

        page_rows.append(
            {
                "document_id": document_id,
                "filename": document_record["filename"],
                "page_index": page_index,
                "page_number": page_index + 1,
                "page_width": page_width,
                "page_height": page_height,
                "preproc_block_count": len(
                    page.get(
                        "preproc_blocks",
                        [],
                    )
                    or []
                ),
                "para_block_count": len(
                    page.get(
                        "para_blocks",
                        [],
                    )
                    or []
                ),
                "discarded_block_count": len(
                    page.get(
                        "discarded_blocks",
                        [],
                    )
                    or []
                ),
            }
        )


pages_df = pd.DataFrame(page_rows)

pages_df

# %%
page_summary = pages_df.groupby(
    "filename",
    as_index=False,
).agg(
    page_count=(
        "page_index",
        "nunique",
    ),
    preproc_blocks=(
        "preproc_block_count",
        "sum",
    ),
    para_blocks=(
        "para_block_count",
        "sum",
    ),
    discarded_blocks=(
        "discarded_block_count",
        "sum",
    ),
    min_page_width=(
        "page_width",
        "min",
    ),
    max_page_width=(
        "page_width",
        "max",
    ),
    min_page_height=(
        "page_height",
        "min",
    ),
    max_page_height=(
        "page_height",
        "max",
    ),
)

page_summary

# %% [markdown]
# ## 9. Níveis de título

# %%
title_blocks = blocks_df[
    blocks_df["block_type"].isin(
        {
            "title",
            "paragraph_title",
            "doc_title",
            "section_title",
        }
    )
    | blocks_df["level"].notna()
].copy()

title_blocks[
    [
        "filename",
        "block_collection",
        "page_number",
        "block_index",
        "block_type",
        "level",
        "score",
        "text",
    ]
].sort_values(
    [
        "filename",
        "page_number",
        "block_index",
        "block_collection",
    ]
)

# %%
title_level_counts = (
    title_blocks.groupby(
        [
            "block_collection",
            "block_type",
            "level",
        ],
        dropna=False,
    )
    .size()
    .rename("count")
    .reset_index()
    .sort_values(
        [
            "block_collection",
            "block_type",
            "level",
        ]
    )
)

title_level_counts

# %% [markdown]
# ## 10. Linhas e spans
#
# Esta tabela preserva a granularidade necessária para diferenciar elementos
# visualmente próximos dentro do mesmo bloco, como autores e filiação.

# %%
line_rows: list[dict[str, Any]] = []
span_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for (
            page_index,
            block_index,
            block,
        ) in iter_blocks(
            document,
            block_collection,
        ):
            for line_index, line in iter_lines(block):
                line_bbox = bbox_metrics(line.get("bbox"))
                line_text = extract_text_from_line(line)

                spans = list(iter_spans(line))

                line_rows.append(
                    {
                        "document_id": document_id,
                        "filename": (document_record["filename"]),
                        "block_collection": (block_collection),
                        "page_index": page_index,
                        "page_number": (page_index + 1),
                        "block_index": block_index,
                        "block_type": block.get("type"),
                        "block_level": block.get("level"),
                        "line_index": line_index,
                        "line_text": line_text,
                        "line_text_length": len(line_text),
                        "span_count": len(spans),
                        **{f"line_{key}": value for key, value in line_bbox.items()},
                    }
                )

                for (
                    span_index,
                    span,
                ) in spans:
                    span_bbox = bbox_metrics(span.get("bbox"))

                    span_text = extract_text_from_span(span)

                    span_rows.append(
                        {
                            "document_id": (document_id),
                            "filename": (document_record["filename"]),
                            "block_collection": (block_collection),
                            "page_index": (page_index),
                            "page_number": (page_index + 1),
                            "block_index": (block_index),
                            "block_type": (block.get("type")),
                            "block_level": (block.get("level")),
                            "line_index": (line_index),
                            "span_index": (span_index),
                            "span_type": (span.get("type")),
                            "span_text": (span_text),
                            "span_text_length": (len(span_text)),
                            "score": (span.get("score")),
                            "cross_page": bool(
                                span.get(
                                    "cross_page",
                                    False,
                                )
                            ),
                            "has_latex": bool(span.get("latex")),
                            "has_html": bool(span.get("html")),
                            "has_image_path": bool(
                                span.get("image_path") or span.get("img_path")
                            ),
                            **{
                                f"span_{key}": (value)
                                for key, value in span_bbox.items()
                            },
                        }
                    )


lines_df = pd.DataFrame(line_rows)

spans_df = pd.DataFrame(span_rows)


lines_df.shape, spans_df.shape

# %%
lines_df.head(20)

# %%
spans_df.head(20)

# %% [markdown]
# ## 11. Tipos de span

# %%
if spans_df.empty:
    span_type_counts = pd.DataFrame(
        columns=[
            "span_type",
            "count",
        ]
    )
else:
    span_type_counts = (
        spans_df.groupby(
            "span_type",
            dropna=False,
        )
        .size()
        .rename("count")
        .reset_index()
        .sort_values(
            "count",
            ascending=False,
        )
        .reset_index(drop=True)
    )

span_type_counts

# %% [markdown]
# ## 12. Blocos com múltiplas linhas
#
# Estes blocos são especialmente importantes para a futura identificação de:
#
# - autores;
# - filiações;
# - endereços;
# - listas;
# - títulos quebrados em mais de uma linha.

# %%
multi_line_blocks = (
    blocks_df[blocks_df["line_count"] > 1][
        [
            "filename",
            "block_collection",
            "page_number",
            "block_index",
            "block_type",
            "level",
            "line_count",
            "span_count",
            "score",
            "text",
        ]
    ]
    .sort_values(
        [
            "filename",
            "page_number",
            "block_index",
            "block_collection",
        ]
    )
    .reset_index(drop=True)
)

multi_line_blocks.head(100)

# %%
multi_line_detail = (
    lines_df.merge(
        multi_line_blocks[
            [
                "filename",
                "block_collection",
                "page_number",
                "block_index",
            ]
        ].drop_duplicates(),
        on=[
            "filename",
            "block_collection",
            "page_number",
            "block_index",
        ],
        how="inner",
    )[
        [
            "filename",
            "block_collection",
            "page_number",
            "block_index",
            "block_type",
            "block_level",
            "line_index",
            "line_text",
            "line_x0",
            "line_y0",
            "line_x1",
            "line_y1",
        ]
    ]
    .sort_values(
        [
            "filename",
            "page_number",
            "block_index",
            "line_index",
            "block_collection",
        ]
    )
    .reset_index(drop=True)
)

multi_line_detail.head(200)

# %% [markdown]
# ## 13. Inspeção da primeira página
#
# A primeira página concentra frequentemente:
#
# - grupo ou evento;
# - título principal;
# - autores;
# - filiação;
# - resumo;
# - palavras-chave.

# %%
first_page_blocks = (
    blocks_df[blocks_df["page_index"] == 0][
        [
            "filename",
            "block_collection",
            "block_index",
            "block_type",
            "level",
            "score",
            "line_count",
            "span_count",
            "x0",
            "y0",
            "x1",
            "y1",
            "text",
        ]
    ]
    .sort_values(
        [
            "filename",
            "block_index",
            "block_collection",
        ]
    )
    .reset_index(drop=True)
)

first_page_blocks

# %%
first_page_lines = (
    lines_df[lines_df["page_index"] == 0][
        [
            "filename",
            "block_collection",
            "block_index",
            "block_type",
            "block_level",
            "line_index",
            "line_text",
            "line_x0",
            "line_y0",
            "line_x1",
            "line_y1",
        ]
    ]
    .sort_values(
        [
            "filename",
            "block_index",
            "line_index",
            "block_collection",
        ]
    )
    .reset_index(drop=True)
)

first_page_lines

# %% [markdown]
# ## 14. Tabelas


# %%
def find_nested_values(
    value: Any,
    target_keys: set[str],
) -> list[tuple[str, Any]]:
    matches: list[tuple[str, Any]] = []

    def walk(
        current: Any,
        path: str,
    ) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{path}.{key}" if path else key

                if key in target_keys:
                    matches.append(
                        (
                            child_path,
                            child,
                        )
                    )

                walk(
                    child,
                    child_path,
                )

        elif isinstance(current, list):
            for index, child in enumerate(current):
                child_path = f"{path}[{index}]"

                walk(
                    child,
                    child_path,
                )

    walk(
        value,
        "",
    )

    return matches


table_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for (
            page_index,
            block_index,
            block,
        ) in iter_blocks(
            document,
            block_collection,
        ):
            nested_html = find_nested_values(
                block,
                {"html"},
            )

            is_table = block.get("type") == "table" or bool(nested_html)

            if not is_table:
                continue

            html_values = [
                str(value)
                for _, value in nested_html
                if isinstance(
                    value,
                    str,
                )
                and value.strip()
            ]

            caption_values = [
                value
                for _, value in find_nested_values(
                    block,
                    {
                        "table_caption",
                        "caption",
                    },
                )
                if value
                not in (
                    None,
                    "",
                    [],
                )
            ]

            image_values = [
                value
                for _, value in find_nested_values(
                    block,
                    {
                        "image_path",
                        "img_path",
                    },
                )
                if value
            ]

            table_rows.append(
                {
                    "document_id": document_id,
                    "filename": document_record["filename"],
                    "block_collection": (block_collection),
                    "page_index": page_index,
                    "page_number": (page_index + 1),
                    "block_index": block_index,
                    "block_type": block.get("type"),
                    "score": block.get("score"),
                    "caption": truncate_text(caption_values),
                    "html": (html_values[0] if html_values else ""),
                    "html_length": sum(len(value) for value in html_values),
                    "image_paths": (
                        " | ".join(
                            map(
                                str,
                                image_values,
                            )
                        )
                    ),
                    "bbox": block.get("bbox"),
                }
            )


tables_df = pd.DataFrame(table_rows)

tables_df

# %%
if not tables_df.empty:
    table_summary = tables_df.groupby(
        "filename",
        as_index=False,
    ).agg(
        table_count=(
            "block_index",
            "count",
        ),
        tables_with_html=(
            "html_length",
            lambda values: int((values > 0).sum()),
        ),
        tables_without_html=(
            "html_length",
            lambda values: int((values == 0).sum()),
        ),
    )
else:
    table_summary = pd.DataFrame(
        columns=[
            "filename",
            "table_count",
            "tables_with_html",
            "tables_without_html",
        ]
    )

table_summary

# %%
for row in tables_df.itertuples(index=False):
    if not row.html:
        continue

    display(Markdown(f"### {row.filename} — página {row.page_number}"))

    display(Markdown(row.html))

# %% [markdown]
# ## 15. Fórmulas

# %%
FORMULA_TYPES = {
    "equation",
    "display_formula",
    "inline_formula",
    "interline_equation",
    "equation_interline",
    "equation_inline",
    "formula",
    "formula_number",
}


formula_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for (
            page_index,
            block_index,
            block,
        ) in iter_blocks(
            document,
            block_collection,
        ):
            nested_latex = find_nested_values(
                block,
                {
                    "latex",
                    "math_content",
                },
            )

            formula_spans = []

            for _, line in iter_lines(block):
                for _, span in iter_spans(line):
                    if span.get("type") in FORMULA_TYPES or span.get("latex"):
                        formula_spans.append(span)

            is_formula = (
                block.get("type") in FORMULA_TYPES
                or bool(nested_latex)
                or bool(formula_spans)
            )

            if not is_formula:
                continue

            latex_values = [
                str(value)
                for _, value in nested_latex
                if isinstance(
                    value,
                    str,
                )
                and value.strip()
            ]

            latex_values.extend(
                str(span.get("latex") or span.get("content") or "")
                for span in formula_spans
                if (span.get("latex") or span.get("content"))
            )

            formula_rows.append(
                {
                    "document_id": document_id,
                    "filename": document_record["filename"],
                    "block_collection": (block_collection),
                    "page_index": page_index,
                    "page_number": (page_index + 1),
                    "block_index": block_index,
                    "block_type": block.get("type"),
                    "score": block.get("score"),
                    "latex": "\n\n".join(dict.fromkeys(latex_values)),
                    "latex_length": sum(len(value) for value in latex_values),
                    "text": (extract_text_from_block(block)),
                    "bbox": block.get("bbox"),
                }
            )


formulas_df = pd.DataFrame(formula_rows)

formulas_df

# %%
if not formulas_df.empty:
    formula_summary = formulas_df.groupby(
        "filename",
        as_index=False,
    ).agg(
        formula_count=(
            "block_index",
            "count",
        ),
        formulas_with_latex=(
            "latex_length",
            lambda values: int((values > 0).sum()),
        ),
        formulas_without_latex=(
            "latex_length",
            lambda values: int((values == 0).sum()),
        ),
    )
else:
    formula_summary = pd.DataFrame(
        columns=[
            "filename",
            "formula_count",
            "formulas_with_latex",
            "formulas_without_latex",
        ]
    )

formula_summary

# %%
for row in formulas_df.itertuples(index=False):
    if not row.latex:
        continue

    display(Markdown(f"### {row.filename} — página {row.page_number}"))

    display(Markdown(f"```latex\n{row.latex}\n```"))

# %% [markdown]
# ## 16. Figuras, gráficos e imagens

# %%
IMAGE_TYPES = {
    "figure",
    "image",
    "chart",
    "figure_body",
    "header_image",
}


image_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for (
            page_index,
            block_index,
            block,
        ) in iter_blocks(
            document,
            block_collection,
        ):
            image_values = [
                value
                for _, value in find_nested_values(
                    block,
                    {
                        "image_path",
                        "img_path",
                    },
                )
                if value
            ]

            is_image = block.get("type") in IMAGE_TYPES or bool(image_values)

            if not is_image:
                continue

            image_rows.append(
                {
                    "document_id": document_id,
                    "filename": document_record["filename"],
                    "block_collection": (block_collection),
                    "page_index": page_index,
                    "page_number": (page_index + 1),
                    "block_index": block_index,
                    "block_type": block.get("type"),
                    "score": block.get("score"),
                    "image_paths": (
                        " | ".join(
                            map(
                                str,
                                image_values,
                            )
                        )
                    ),
                    "text": (extract_text_from_block(block)),
                    "bbox": block.get("bbox"),
                }
            )


images_df = pd.DataFrame(image_rows)

images_df

# %% [markdown]
# ## 17. Blocos descartados
#
# Cabeçalhos, rodapés e números de página devem aparecer principalmente em
# `discarded_blocks`.

# %%
discarded_df = (
    blocks_df[blocks_df["block_collection"] == "discarded_blocks"][
        [
            "filename",
            "page_number",
            "block_index",
            "block_type",
            "score",
            "line_count",
            "span_count",
            "text",
            "x0",
            "y0",
            "x1",
            "y1",
        ]
    ]
    .sort_values(
        [
            "filename",
            "page_number",
            "block_index",
        ]
    )
    .reset_index(drop=True)
)

discarded_df

# %%
discarded_type_counts = (
    discarded_df.groupby(
        "block_type",
        dropna=False,
    )
    .size()
    .rename("count")
    .reset_index()
    .sort_values(
        "count",
        ascending=False,
    )
    .reset_index(drop=True)
)

discarded_type_counts

# %% [markdown]
# ## 18. Cabeçalhos, rodapés e números de página fora de `discarded_blocks`
#
# Esta verificação identifica elementos potencialmente vazando para o conteúdo
# principal.

# %%
NOISE_TYPES = {
    "header",
    "footer",
    "page_number",
    "number",
}


noise_blocks = (
    blocks_df[blocks_df["block_type"].isin(NOISE_TYPES)][
        [
            "filename",
            "block_collection",
            "page_number",
            "block_index",
            "block_type",
            "score",
            "text",
        ]
    ]
    .sort_values(
        [
            "filename",
            "page_number",
            "block_index",
            "block_collection",
        ]
    )
    .reset_index(drop=True)
)

noise_blocks

# %%
noise_leaks = noise_blocks[
    noise_blocks["block_collection"] != "discarded_blocks"
].copy()

noise_leaks

# %% [markdown]
# ## 19. Continuidade entre páginas

# %%
cross_page_spans = (
    spans_df[spans_df["cross_page"]][
        [
            "filename",
            "block_collection",
            "page_number",
            "block_index",
            "block_type",
            "line_index",
            "span_index",
            "span_type",
            "span_text",
            "score",
        ]
    ]
    .sort_values(
        [
            "filename",
            "page_number",
            "block_index",
            "line_index",
            "span_index",
        ]
    )
    .reset_index(drop=True)
)

cross_page_spans

# %%
cross_page_summary = (
    cross_page_spans.groupby(
        "filename",
        as_index=False,
    ).agg(
        cross_page_span_count=(
            "span_index",
            "count",
        ),
        affected_pages=(
            "page_number",
            "nunique",
        ),
    )
    if not cross_page_spans.empty
    else pd.DataFrame(
        columns=[
            "filename",
            "cross_page_span_count",
            "affected_pages",
        ]
    )
)

cross_page_summary

# %% [markdown]
# ## 20. Scores dos blocos e spans

# %%
block_score_summary = (
    blocks_df.groupby(
        [
            "block_collection",
            "block_type",
        ],
        dropna=False,
    )
    .agg(
        count=(
            "score",
            "size",
        ),
        score_count=(
            "score",
            "count",
        ),
        score_min=(
            "score",
            "min",
        ),
        score_mean=(
            "score",
            "mean",
        ),
        score_median=(
            "score",
            "median",
        ),
        score_max=(
            "score",
            "max",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "block_collection",
            "score_mean",
        ],
        ascending=[
            True,
            True,
        ],
    )
)

block_score_summary

# %%
LOW_SCORE_THRESHOLD = 0.80


low_score_blocks = (
    blocks_df[blocks_df["score"].notna() & (blocks_df["score"] < LOW_SCORE_THRESHOLD)][
        [
            "filename",
            "block_collection",
            "page_number",
            "block_index",
            "block_type",
            "score",
            "text",
        ]
    ]
    .sort_values(
        [
            "score",
            "filename",
            "page_number",
        ]
    )
    .reset_index(drop=True)
)

low_score_blocks

# %%
if spans_df.empty:
    span_score_summary = pd.DataFrame()
else:
    span_score_summary = (
        spans_df.groupby(
            "span_type",
            dropna=False,
        )
        .agg(
            count=(
                "score",
                "size",
            ),
            score_count=(
                "score",
                "count",
            ),
            score_min=(
                "score",
                "min",
            ),
            score_mean=(
                "score",
                "mean",
            ),
            score_median=(
                "score",
                "median",
            ),
            score_max=(
                "score",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "score_mean",
            ascending=True,
        )
    )

span_score_summary

# %% [markdown]
# ## 21. Campos encontrados nos blocos
#
# Este inventário evita assumir prematuramente um schema fixo.


# %%
def collect_dict_keys(
    items: Iterable[dict[str, Any]],
) -> Counter[str]:
    counter: Counter[str] = Counter()

    for item in items:
        counter.update(item.keys())

    return counter


block_key_rows: list[dict[str, Any]] = []

for document_id, document_record in loaded_documents.items():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        blocks = [
            block
            for _, _, block in iter_blocks(
                document,
                block_collection,
            )
        ]

        key_counts = collect_dict_keys(blocks)

        for key, count in key_counts.items():
            block_key_rows.append(
                {
                    "document_id": document_id,
                    "filename": document_record["filename"],
                    "block_collection": (block_collection),
                    "key": key,
                    "count": count,
                }
            )


block_keys_df = pd.DataFrame(block_key_rows)

block_keys_df

# %%
block_key_summary = (
    block_keys_df.groupby(
        [
            "block_collection",
            "key",
        ],
        as_index=False,
    )
    .agg(
        document_count=(
            "document_id",
            "nunique",
        ),
        occurrence_count=(
            "count",
            "sum",
        ),
    )
    .sort_values(
        [
            "block_collection",
            "occurrence_count",
            "key",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )
    .reset_index(drop=True)
)

block_key_summary

# %% [markdown]
# ## 22. Campos encontrados em linhas e spans

# %%
line_key_counter: Counter[str] = Counter()
span_key_counter: Counter[str] = Counter()

for document_record in loaded_documents.values():
    document = document_record["data"]

    for block_collection in BLOCK_FIELDS:
        for _, _, block in iter_blocks(
            document,
            block_collection,
        ):
            for _, line in iter_lines(block):
                line_key_counter.update(line.keys())

                for _, span in iter_spans(line):
                    span_key_counter.update(span.keys())


line_keys_df = pd.DataFrame(
    [
        {
            "key": key,
            "count": count,
        }
        for key, count in line_key_counter.most_common()
    ]
)

span_keys_df = pd.DataFrame(
    [
        {
            "key": key,
            "count": count,
        }
        for key, count in span_key_counter.most_common()
    ]
)


line_keys_df

# %%
span_keys_df

# %% [markdown]
# ## 23. Duplicação entre `preproc_blocks` e `para_blocks`
#
# O `middle.json` costuma manter versões diferentes dos blocos antes e depois
# do agrupamento em parágrafos. Esta comparação mede quanto conteúdo textual
# aparece em ambas as coleções.


# %%
def normalized_text(
    value: Any,
) -> str:
    return " ".join(str(value or "").casefold().split())


duplicate_rows: list[dict[str, Any]] = []

for (
    filename,
    page_number,
), page_group in blocks_df.groupby(
    [
        "filename",
        "page_number",
    ]
):
    preproc = page_group[page_group["block_collection"] == "preproc_blocks"].copy()

    para = page_group[page_group["block_collection"] == "para_blocks"].copy()

    preproc["normalized_text"] = preproc["text"].map(normalized_text)

    para["normalized_text"] = para["text"].map(normalized_text)

    preproc = preproc[preproc["normalized_text"] != ""]

    para = para[para["normalized_text"] != ""]

    para_texts = set(para["normalized_text"])

    matching_preproc = preproc[preproc["normalized_text"].isin(para_texts)]

    duplicate_rows.append(
        {
            "filename": filename,
            "page_number": page_number,
            "preproc_text_blocks": len(preproc),
            "para_text_blocks": len(para),
            "exact_text_matches": len(matching_preproc),
            "preproc_match_ratio": (
                len(matching_preproc) / len(preproc) if len(preproc) else None
            ),
        }
    )


duplicate_summary = pd.DataFrame(duplicate_rows)

duplicate_summary

# %% [markdown]
# ## 24. Possíveis anomalias estruturais

# %%
anomaly_rows: list[dict[str, Any]] = []


for row in blocks_df.itertuples(index=False):
    if not row.block_type:
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("block_type_missing"),
                "details": truncate_text(row.text),
            }
        )

    if (
        row.text_length == 0
        and not row.has_html
        and not row.has_latex
        and not row.has_image_path
        and not row.has_blocks
    ):
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("empty_block"),
                "details": (f"type={row.block_type}"),
            }
        )

    if row.has_bbox and (
        row.width is None or row.height is None or row.width <= 0 or row.height <= 0
    ):
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("invalid_bbox"),
                "details": (f"bbox=[{row.x0}, {row.y0}, {row.x1}, {row.y1}]"),
            }
        )

    if row.block_type in NOISE_TYPES and row.block_collection != "discarded_blocks":
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("noise_outside_discarded"),
                "details": truncate_text(row.text),
            }
        )


for row in tables_df.itertuples(index=False):
    if row.html_length == 0:
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("table_without_html"),
                "details": truncate_text(row.caption),
            }
        )


for row in formulas_df.itertuples(index=False):
    if row.latex_length == 0:
        anomaly_rows.append(
            {
                "filename": row.filename,
                "page_number": row.page_number,
                "block_collection": (row.block_collection),
                "block_index": row.block_index,
                "anomaly": ("formula_without_latex"),
                "details": truncate_text(row.text),
            }
        )


anomalies_df = pd.DataFrame(anomaly_rows)

if not anomalies_df.empty:
    anomalies_df = anomalies_df.sort_values(
        [
            "filename",
            "page_number",
            "block_index",
            "anomaly",
        ]
    ).reset_index(drop=True)

anomalies_df

# %%
if anomalies_df.empty:
    anomaly_summary = pd.DataFrame(
        columns=[
            "anomaly",
            "count",
        ]
    )
else:
    anomaly_summary = (
        anomalies_df.groupby("anomaly")
        .size()
        .rename("count")
        .reset_index()
        .sort_values(
            "count",
            ascending=False,
        )
        .reset_index(drop=True)
    )

anomaly_summary

# %% [markdown]
# ## 25. Resumo consolidado por documento

# %%
document_summary = (
    page_summary.merge(
        table_summary,
        on="filename",
        how="left",
    )
    .merge(
        formula_summary,
        on="filename",
        how="left",
    )
    .merge(
        cross_page_summary,
        on="filename",
        how="left",
    )
)


for column in (
    "table_count",
    "tables_with_html",
    "tables_without_html",
    "formula_count",
    "formulas_with_latex",
    "formulas_without_latex",
    "cross_page_span_count",
    "affected_pages",
):
    if column in document_summary.columns:
        document_summary[column] = document_summary[column].fillna(0).astype(int)


document_summary

# %% [markdown]
# ## 26. Relatório textual rápido

# %%
total_documents = len(loaded_documents)

total_pages = int(pages_df["page_index"].count())

total_blocks = len(blocks_df)

total_lines = len(lines_df)

total_spans = len(spans_df)

total_tables = len(tables_df)

total_formulas = len(formulas_df)

total_cross_page = len(cross_page_spans)

total_anomalies = len(anomalies_df)


display(
    Markdown(
        f"""
## Resultado da inspeção

- Documentos carregados: **{total_documents}**
- Páginas inspecionadas: **{total_pages}**
- Blocos inventariados: **{total_blocks}**
- Linhas inventariadas: **{total_lines}**
- Spans inventariados: **{total_spans}**
- Tabelas identificadas: **{total_tables}**
- Fórmulas identificadas: **{total_formulas}**
- Spans com continuidade entre páginas: **{total_cross_page}**
- Anomalias estruturais registradas: **{total_anomalies}**
"""
    )
)

# %% [markdown]
# ## 27. Exportação dos relatórios

# %%
EXPORTS: dict[str, pd.DataFrame] = {
    "validation.csv": validation_df,
    "middle_manifest.csv": middle_manifest,
    "documents.csv": document_summary,
    "pages.csv": pages_df,
    "blocks.csv": blocks_df,
    "block_type_counts.csv": (block_type_counts),
    "titles.csv": title_blocks,
    "lines.csv": lines_df,
    "spans.csv": spans_df,
    "span_type_counts.csv": (span_type_counts),
    "multi_line_blocks.csv": (multi_line_blocks),
    "multi_line_detail.csv": (multi_line_detail),
    "first_page_blocks.csv": (first_page_blocks),
    "first_page_lines.csv": (first_page_lines),
    "tables.csv": tables_df,
    "formulas.csv": formulas_df,
    "images.csv": images_df,
    "discarded_blocks.csv": (discarded_df),
    "noise_blocks.csv": noise_blocks,
    "noise_leaks.csv": noise_leaks,
    "cross_page_spans.csv": (cross_page_spans),
    "block_score_summary.csv": (block_score_summary),
    "low_score_blocks.csv": (low_score_blocks),
    "span_score_summary.csv": (span_score_summary),
    "block_keys.csv": block_keys_df,
    "block_key_summary.csv": (block_key_summary),
    "line_keys.csv": line_keys_df,
    "span_keys.csv": span_keys_df,
    "duplicate_summary.csv": (duplicate_summary),
    "anomalies.csv": anomalies_df,
    "anomaly_summary.csv": (anomaly_summary),
}


exported_paths: list[Path] = []

for filename, dataframe in EXPORTS.items():
    export_path = REPORTS_ROOT / filename

    dataframe.to_csv(
        export_path,
        index=False,
        encoding="utf-8-sig",
    )

    exported_paths.append(export_path)


pd.DataFrame({"exported_path": [str(path) for path in exported_paths]})

# %% [markdown]
# ## 28. Snapshot JSON do schema observado
#
# Este arquivo registra apenas o inventário estrutural. Ele não representa
# ainda o schema definitivo do IR.

# %%
schema_snapshot = {
    "documents": total_documents,
    "pages": total_pages,
    "blocks": total_blocks,
    "lines": total_lines,
    "spans": total_spans,
    "block_collections": sorted(
        blocks_df["block_collection"].dropna().unique().tolist()
    ),
    "block_types": sorted(
        str(value) for value in blocks_df["block_type"].dropna().unique().tolist()
    ),
    "span_types": sorted(
        str(value) for value in spans_df["span_type"].dropna().unique().tolist()
    ),
    "block_keys": sorted(block_keys_df["key"].dropna().unique().tolist()),
    "line_keys": sorted(line_keys_df["key"].dropna().unique().tolist()),
    "span_keys": sorted(span_keys_df["key"].dropna().unique().tolist()),
    "formula_types": sorted(FORMULA_TYPES),
    "image_types": sorted(IMAGE_TYPES),
    "noise_types": sorted(NOISE_TYPES),
}


SCHEMA_SNAPSHOT_PATH = REPORTS_ROOT / "observed_schema.json"


with SCHEMA_SNAPSHOT_PATH.open(
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        schema_snapshot,
        file,
        ensure_ascii=False,
        indent=2,
    )


SCHEMA_SNAPSHOT_PATH

# %% [markdown]
# ## 29. Critérios para a próxima etapa
#
# A construção do IR poderá partir de `para_blocks`, preservando referências
# para os elementos originais de `preproc_blocks`.
#
# Antes disso, a próxima etapa deverá decidir explicitamente:
#
# 1. qual coleção de blocos será a fonte textual canônica;
# 2. como representar linhas e spans no IR;
# 3. como preservar `bbox`, página e ordem de leitura;
# 4. como representar tabelas, figuras e fórmulas;
# 5. como registrar blocos descartados sem misturá-los ao conteúdo;
# 6. como tratar blocos com continuidade entre páginas;
# 7. como representar candidatos a metadados sem classificá-los cedo demais.

# %%
print("Inspeção concluída.")
print(f"Relatórios: {REPORTS_ROOT}")
print(f"Schema observado: {SCHEMA_SNAPSHOT_PATH}")
