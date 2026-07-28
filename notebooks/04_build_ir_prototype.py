# %% [markdown]
# # 04 — Build IR Prototype
#
# Converte `middle.json` do MinerU em um IR mínimo e estável.
#
# Escopo:
#
# - `para_blocks` é a única fonte canônica de conteúdo;
# - `discarded_blocks` é preservado separadamente;
# - `preproc_blocks` nunca é importado;
# - nenhuma heurística semântica;
# - nenhuma etapa de chunking;
# - campos desconhecidos são preservados em `attributes`.

# %%
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

# %% [markdown]
# ## Configuração

# %%
PROJECT_ROOT = Path.cwd()

DATA_DIR = PROJECT_ROOT / "artifacts" / "mineru" / "smoke"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

MIDDLE_GLOB = "**/*middle.json"
OUTPUT_DIR = ARTIFACTS_DIR / "ir_prototype"

MAX_DOCUMENTS: int | None = 5

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# %% [markdown]
# ## Modelos do IR
#
# O IR mantém apenas a estrutura física/lógica já produzida pelo MinerU.
# Sem classes semânticas como `Heading`, `Paragraph`, `Section` etc.


# %%
class IRModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class SpanIR(IRModel):
    id: str

    type: str | None = None
    text: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    latex: str | None = None
    html: str | None = None
    image_path: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LineIR(IRModel):
    id: str

    bbox: list[float] | None = None
    score: float | None = None
    spans: list[SpanIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class BlockIR(IRModel):
    id: str
    block_index: int | None = None

    type: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    level: int | None = None
    cross_page: bool | None = None
    image_path: str | None = None
    latex: str | None = None
    html: str | None = None
    lines: list[LineIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class PageIR(IRModel):
    id: str
    page: int

    width: float | None = None
    height: float | None = None
    blocks: list[BlockIR] = Field(default_factory=list)
    discarded_blocks: list[BlockIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class DocumentIR(IRModel):
    id: str
    source_path: str
    source_name: str
    source_sha256: str

    backend: str | None = None
    backend_version: str | None = None

    pages: list[PageIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


# %% [markdown]
# ## Campos conhecidos
#
# Todo campo não listado aqui vai para `attributes`.

# %%
ROOT_FIELDS = {
    "pdf_info",
    "pages",
    "page_info",
    "para_blocks",
    "discarded_blocks",
    "preproc_blocks",
    "_backend",
    "_version_name",
}

SPAN_FIELDS = {
    "type",
    "text",
    "content",
    "bbox",
    "score",
    "latex",
    "html",
    "image_path",
}

LINE_FIELDS = {
    "bbox",
    "score",
    "spans",
}

BLOCK_FIELDS = {
    "type",
    "block_type",
    "index",
    "bbox",
    "score",
    "level",
    "cross_page",
    "image_path",
    "latex",
    "html",
    "lines",
}

PAGE_FIELDS = {
    "page",
    "page_idx",
    "page_no",
    "page_number",
    "width",
    "height",
    "page_size",
    "para_blocks",
    "discarded_blocks",
    "preproc_blocks",
}


# %% [markdown]
# ## Helpers de normalização


# %%
def unknown_attributes(
    payload: dict[str, Any],
    known_fields: set[str],
) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in known_fields}


def first_present(
    payload: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def as_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes"}:
            return True

        if normalized in {"false", "0", "no"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return None


def as_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def extract_page_size(
    page_payload: dict[str, Any],
) -> tuple[float | None, float | None]:
    width = as_float(page_payload.get("width"))
    height = as_float(page_payload.get("height"))

    page_size = page_payload.get("page_size")

    if (
        (width is None or height is None)
        and isinstance(page_size, (list, tuple))
        and len(page_size) >= 2
    ):
        width = width if width is not None else as_float(page_size[0])
        height = height if height is not None else as_float(page_size[1])

    return width, height


# %% [markdown]
# ## Conversão


# %%
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def child_id(parent_id: str, kind: str, index: int) -> str:
    return f"{parent_id}:{kind}{index:04d}"


def build_span_ir(
    payload: dict[str, Any],
    *,
    span_id: str,
) -> SpanIR:
    text = first_present(payload, "text", "content")

    return SpanIR(
        id=span_id,
        type=payload.get("type"),
        text=text if isinstance(text, str) else None,
        bbox=as_bbox(payload.get("bbox")),
        score=as_float(payload.get("score")),
        latex=payload.get("latex") if isinstance(payload.get("latex"), str) else None,
        html=payload.get("html") if isinstance(payload.get("html"), str) else None,
        image_path=(
            payload.get("image_path")
            if isinstance(payload.get("image_path"), str)
            else None
        ),
        attributes=unknown_attributes(payload, SPAN_FIELDS),
    )


def build_line_ir(
    payload: dict[str, Any],
    *,
    line_id: str,
) -> LineIR:
    raw_spans = payload.get("spans", [])

    return LineIR(
        id=line_id,
        bbox=as_bbox(payload.get("bbox")),
        score=as_float(payload.get("score")),
        spans=[
            build_span_ir(
                span,
                span_id=child_id(line_id, "s", span_index),
            )
            for span_index, span in enumerate(raw_spans)
            if isinstance(span, dict)
        ],
        attributes=unknown_attributes(payload, LINE_FIELDS),
    )


def build_block_ir(
    payload: dict[str, Any],
    *,
    block_id: str,
    fallback_index: int,
) -> BlockIR:
    raw_lines = payload.get("lines", [])

    return BlockIR(
        id=block_id,
        block_index=as_int(payload.get("index"))
        if payload.get("index") is not None
        else fallback_index,
        type=first_present(payload, "type", "block_type"),
        bbox=as_bbox(payload.get("bbox")),
        score=as_float(payload.get("score")),
        level=as_int(payload.get("level")),
        cross_page=as_bool(payload.get("cross_page")),
        image_path=(
            payload.get("image_path")
            if isinstance(payload.get("image_path"), str)
            else None
        ),
        latex=payload.get("latex") if isinstance(payload.get("latex"), str) else None,
        html=payload.get("html") if isinstance(payload.get("html"), str) else None,
        lines=[
            build_line_ir(
                line,
                line_id=child_id(block_id, "l", line_index),
            )
            for line_index, line in enumerate(raw_lines)
            if isinstance(line, dict)
        ],
        attributes=unknown_attributes(payload, BLOCK_FIELDS),
    )


def resolve_page_number(
    page_payload: dict[str, Any],
    fallback_index: int,
) -> int:
    page_number = first_present(
        page_payload,
        "page",
        "page_idx",
        "page_no",
        "page_number",
    )

    parsed = as_int(page_number)

    return fallback_index if parsed is None else parsed


def build_page_ir(
    page_payload: dict[str, Any],
    *,
    page_id: str,
    fallback_index: int,
) -> PageIR:
    raw_blocks = page_payload.get("para_blocks", [])
    raw_discarded = page_payload.get("discarded_blocks", [])

    width, height = extract_page_size(page_payload)

    return PageIR(
        id=page_id,
        page=resolve_page_number(
            page_payload,
            fallback_index,
        ),
        width=width,
        height=height,
        blocks=[
            build_block_ir(
                block,
                block_id=child_id(page_id, "b", block_index),
                fallback_index=block_index,
            )
            for block_index, block in enumerate(raw_blocks)
            if isinstance(block, dict)
        ],
        discarded_blocks=[
            build_block_ir(
                block,
                block_id=child_id(page_id, "d", block_index),
                fallback_index=block_index,
            )
            for block_index, block in enumerate(raw_discarded)
            if isinstance(block, dict)
        ],
        attributes=unknown_attributes(page_payload, PAGE_FIELDS),
    )


def extract_page_payloads(
    middle_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = (
        middle_payload.get("pdf_info"),
        middle_payload.get("pages"),
        middle_payload.get("page_info"),
    )

    for candidate in candidates:
        if isinstance(candidate, list):
            return [page for page in candidate if isinstance(page, dict)]

    if any(
        key in middle_payload
        for key in {"para_blocks", "discarded_blocks", "preproc_blocks"}
    ):
        return [middle_payload]

    raise ValueError(
        "Não foi possível localizar as páginas no middle.json. "
        "Chaves esperadas: pdf_info, pages ou page_info."
    )


def build_document_ir(
    middle_path: Path,
) -> tuple[DocumentIR, dict[str, Any]]:
    with middle_path.open("r", encoding="utf-8") as file:
        middle_payload = json.load(file)

    if not isinstance(middle_payload, dict):
        raise TypeError(f"Raiz inválida em {middle_path}: esperado objeto JSON.")

    page_payloads = extract_page_payloads(middle_payload)

    source_sha256 = sha256_file(middle_path)
    document_id = source_sha256[:16]

    document = DocumentIR(
        id=document_id,
        source_path=str(middle_path),
        source_name=middle_path.stem.removesuffix("_middle"),
        source_sha256=source_sha256,
        backend=middle_payload.get("_backend"),
        backend_version=middle_payload.get("_version_name"),
        pages=[
            build_page_ir(
                page_payload,
                page_id=child_id(document_id, "p", page_index),
                fallback_index=page_index,
            )
            for page_index, page_payload in enumerate(page_payloads)
        ],
        attributes=unknown_attributes(
            middle_payload,
            ROOT_FIELDS,
        ),
    )

    return document, middle_payload


# %% [markdown]
# ## Métricas e validações


# %%
def source_counts(
    middle_path: Path,
) -> dict[str, int]:
    with middle_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    pages = extract_page_payloads(payload)

    return {
        "pages": len(pages),
        "blocks": sum(
            len(page.get("para_blocks", []))
            for page in pages
            if isinstance(page.get("para_blocks", []), list)
        ),
        "discarded_blocks": sum(
            len(page.get("discarded_blocks", []))
            for page in pages
            if isinstance(page.get("discarded_blocks", []), list)
        ),
        "preproc_blocks": sum(
            len(page.get("preproc_blocks", []))
            for page in pages
            if isinstance(page.get("preproc_blocks", []), list)
        ),
    }


def ir_counts(document: DocumentIR) -> dict[str, int]:
    return {
        "pages": len(document.pages),
        "blocks": sum(len(page.blocks) for page in document.pages),
        "discarded_blocks": sum(len(page.discarded_blocks) for page in document.pages),
    }


def iter_blocks(
    document: DocumentIR,
    *,
    include_discarded: bool = True,
) -> Iterable[BlockIR]:
    for page in document.pages:
        yield from page.blocks

        if include_discarded:
            yield from page.discarded_blocks


def block_text(block: BlockIR) -> str:
    return "\n".join(
        span.text for line in block.lines for span in line.spans if span.text
    )


def block_fingerprint(block: BlockIR) -> str:
    payload = {
        "type": block.type,
        "bbox": block.bbox,
        "text": block_text(block),
        "latex": block.latex,
        "html": block.html,
        "image_path": block.image_path,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def duplicate_summary(
    document: DocumentIR,
) -> dict[str, int]:
    content_fingerprints = [
        block_fingerprint(block) for page in document.pages for block in page.blocks
    ]

    discarded_fingerprints = [
        block_fingerprint(block)
        for page in document.pages
        for block in page.discarded_blocks
    ]

    content_counts = Counter(content_fingerprints)
    discarded_counts = Counter(discarded_fingerprints)

    duplicated_content = sum(
        count - 1 for count in content_counts.values() if count > 1
    )

    overlap = len(set(content_fingerprints) & set(discarded_fingerprints))

    return {
        "duplicated_content_blocks": duplicated_content,
        "content_discarded_overlap": overlap,
    }


def validate_document_ir(
    middle_path: Path,
    document: DocumentIR,
) -> dict[str, Any]:
    source = source_counts(middle_path)
    target = ir_counts(document)

    serialized = document.model_dump_json(
        exclude_none=True,
    )

    restored = DocumentIR.model_validate_json(serialized)

    checks = {
        "page_count_matches": source["pages"] == target["pages"],
        "block_count_matches": source["blocks"] == target["blocks"],
        "discarded_count_matches": (
            source["discarded_blocks"] == target["discarded_blocks"]
        ),
        "roundtrip_matches": restored == document,
        "serializable": bool(serialized),
        "preproc_not_serialized": (
            '"preproc_blocks"' not in serialized
            and '"preproc_blocks":' not in serialized
        ),
    }

    duplicates = duplicate_summary(document)

    return {
        "source_path": str(middle_path),
        "source_counts": source,
        "ir_counts": target,
        "checks": checks,
        "duplicates": duplicates,
        "valid": all(checks.values()),
    }


# %% [markdown]
# ## Persistência


# %%
def write_document_ir(
    document: DocumentIR,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        document.model_dump_json(
            indent=2,
            exclude_none=True,
        ),
        encoding="utf-8",
    )


def write_json(
    payload: Any,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# %% [markdown]
# ## Descoberta dos documentos processados

# %%
middle_paths = sorted(DATA_DIR.glob(MIDDLE_GLOB))

if MAX_DOCUMENTS is not None:
    middle_paths = middle_paths[:MAX_DOCUMENTS]

print(f"middle.json encontrados: {len(middle_paths)}")

for path in middle_paths:
    print(path)


# %% [markdown]
# ## Conversão dos documentos

# %%
documents: list[DocumentIR] = []
validation_reports: list[dict[str, Any]] = []

for middle_path in middle_paths:
    document = build_document_ir(middle_path)

    relative_parent = middle_path.parent.relative_to(DATA_DIR)
    output_path = OUTPUT_DIR / relative_parent / "document_ir.json"

    write_document_ir(document, output_path)

    validation = validate_document_ir(
        middle_path,
        document,
    )

    documents.append(document)
    validation_reports.append(validation)

    print(
        f"{middle_path}: "
        f"pages={len(document.pages)} "
        f"blocks={sum(len(page.blocks) for page in document.pages)} "
        f"discarded={sum(len(page.discarded_blocks) for page in document.pages)} "
        f"valid={validation['valid']}"
    )


# %% [markdown]
# ## Relatório consolidado

# %%
summary = {
    "documents": len(documents),
    "valid_documents": sum(report["valid"] for report in validation_reports),
    "invalid_documents": sum(not report["valid"] for report in validation_reports),
    "pages": sum(len(document.pages) for document in documents),
    "blocks": sum(
        len(page.blocks) for document in documents for page in document.pages
    ),
    "discarded_blocks": sum(
        len(page.discarded_blocks) for document in documents for page in document.pages
    ),
    "source_preproc_blocks_ignored": sum(
        report["source_counts"]["preproc_blocks"] for report in validation_reports
    ),
    "duplicated_content_blocks": sum(
        report["duplicates"]["duplicated_content_blocks"]
        for report in validation_reports
    ),
    "content_discarded_overlap": sum(
        report["duplicates"]["content_discarded_overlap"]
        for report in validation_reports
    ),
}

write_json(
    validation_reports,
    OUTPUT_DIR / "validation_report.json",
)

write_json(
    summary,
    OUTPUT_DIR / "summary.json",
)

summary


# %% [markdown]
# ## Tipos observados no IR

# %%
block_type_counts = Counter(
    block.type or "<none>" for document in documents for block in iter_blocks(document)
)

span_type_counts = Counter(
    span.type or "<none>"
    for document in documents
    for block in iter_blocks(document)
    for line in block.lines
    for span in line.spans
)

observed_types = {
    "block_types": dict(block_type_counts.most_common()),
    "span_types": dict(span_type_counts.most_common()),
}

write_json(
    observed_types,
    OUTPUT_DIR / "observed_types.json",
)

observed_types


# %% [markdown]
# ## Falhar explicitamente em caso de inconsistência

# %%
invalid_reports = [report for report in validation_reports if not report["valid"]]

if invalid_reports:
    raise AssertionError(
        json.dumps(
            invalid_reports,
            ensure_ascii=False,
            indent=2,
        )
    )

print("Todos os documentos foram convertidos e validados.")
