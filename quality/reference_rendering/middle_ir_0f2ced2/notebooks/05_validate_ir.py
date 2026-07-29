# %% [markdown]
# # 05 — Validate IR
#
# Validação em lote do IR gerado a partir do `middle.json` do MinerU.
#
# Objetivos:
#
# - validar integridade estrutural;
# - detectar perda de blocos;
# - confirmar ausência de `preproc_blocks`;
# - medir desempenho;
# - observar novos tipos de blocos e spans;
# - inventariar atributos desconhecidos;
# - produzir relatórios de regressão do parser.
#
# Este notebook não enriquece semanticamente o documento e não realiza chunking.

# %%
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

# %% [markdown]
# ## Configuração

# %%
PROJECT_ROOT = Path.cwd()

DATA_DIR = PROJECT_ROOT / "artifacts" / "mineru" / "smoke"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

MIDDLE_GLOB = "**/*_middle.json"
OUTPUT_DIR = ARTIFACTS_DIR / "ir_validation"

MAX_DOCUMENTS: int | None = 120
FAIL_ON_INVALID = True

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# %% [markdown]
# ## IR mínimo
#
# Mantido localmente neste notebook para preservar sua execução isolada.
# Quando o IR for movido para `src/`, substituir estas classes por imports.


# %%
class IRModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class SpanIR(IRModel):
    type: str | None = None
    text: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    latex: str | None = None
    html: str | None = None
    image_path: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LineIR(IRModel):
    bbox: list[float] | None = None
    score: float | None = None
    spans: list[SpanIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class BlockIR(IRModel):
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
    page: int
    width: float | None = None
    height: float | None = None
    blocks: list[BlockIR] = Field(default_factory=list)
    discarded_blocks: list[BlockIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class DocumentIR(IRModel):
    source_path: str
    source_name: str
    pages: list[PageIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


# %% [markdown]
# ## Campos conhecidos

# %%
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

ROOT_FIELDS = {
    "pdf_info",
    "pages",
    "page_info",
    "para_blocks",
    "discarded_blocks",
    "preproc_blocks",
}


# %% [markdown]
# ## Helpers


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

    raise ValueError("Não foi possível localizar páginas no middle.json.")


def percentile(
    values: list[float],
    quantile: float,
) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    weight = position - lower

    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# %% [markdown]
# ## Conversão


# %%
def build_span_ir(payload: dict[str, Any]) -> SpanIR:
    text = first_present(payload, "text", "content")

    return SpanIR(
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


def build_line_ir(payload: dict[str, Any]) -> LineIR:
    raw_spans = payload.get("spans", [])

    return LineIR(
        bbox=as_bbox(payload.get("bbox")),
        score=as_float(payload.get("score")),
        spans=[build_span_ir(span) for span in raw_spans if isinstance(span, dict)],
        attributes=unknown_attributes(payload, LINE_FIELDS),
    )


def build_block_ir(payload: dict[str, Any]) -> BlockIR:
    raw_lines = payload.get("lines", [])

    return BlockIR(
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
        lines=[build_line_ir(line) for line in raw_lines if isinstance(line, dict)],
        attributes=unknown_attributes(payload, BLOCK_FIELDS),
    )


def resolve_page_number(
    page_payload: dict[str, Any],
    fallback_index: int,
) -> int:
    value = first_present(
        page_payload,
        "page",
        "page_idx",
        "page_no",
        "page_number",
    )

    parsed = as_int(value)

    return fallback_index if parsed is None else parsed


def build_page_ir(
    page_payload: dict[str, Any],
    fallback_index: int,
) -> PageIR:
    raw_blocks = page_payload.get("para_blocks", [])
    raw_discarded = page_payload.get("discarded_blocks", [])

    width, height = extract_page_size(page_payload)

    return PageIR(
        page=resolve_page_number(page_payload, fallback_index),
        width=width,
        height=height,
        blocks=[
            build_block_ir(block) for block in raw_blocks if isinstance(block, dict)
        ],
        discarded_blocks=[
            build_block_ir(block) for block in raw_discarded if isinstance(block, dict)
        ],
        attributes=unknown_attributes(page_payload, PAGE_FIELDS),
    )


def build_document_ir(
    middle_path: Path,
) -> tuple[DocumentIR, dict[str, Any]]:
    with middle_path.open("r", encoding="utf-8") as file:
        middle_payload = json.load(file)

    if not isinstance(middle_payload, dict):
        raise TypeError(f"Raiz inválida em {middle_path}: esperado objeto JSON.")

    page_payloads = extract_page_payloads(middle_payload)

    document = DocumentIR(
        source_path=str(middle_path),
        source_name=middle_path.stem.removesuffix("_middle"),
        pages=[
            build_page_ir(page_payload, fallback_index=index)
            for index, page_payload in enumerate(page_payloads)
        ],
        attributes=unknown_attributes(middle_payload, ROOT_FIELDS),
    )

    return document, middle_payload


# %% [markdown]
# ## Iteradores e fingerprints


# %%
def iter_content_blocks(
    document: DocumentIR,
) -> Iterable[BlockIR]:
    for page in document.pages:
        yield from page.blocks


def iter_discarded_blocks(
    document: DocumentIR,
) -> Iterable[BlockIR]:
    for page in document.pages:
        yield from page.discarded_blocks


def iter_all_blocks(
    document: DocumentIR,
) -> Iterable[BlockIR]:
    yield from iter_content_blocks(document)
    yield from iter_discarded_blocks(document)


def iter_lines(
    document: DocumentIR,
) -> Iterable[LineIR]:
    for block in iter_all_blocks(document):
        yield from block.lines


def iter_spans(
    document: DocumentIR,
) -> Iterable[SpanIR]:
    for line in iter_lines(document):
        yield from line.spans


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

    return sha256_text(serialized)


# %% [markdown]
# ## Métricas do documento


# %%
def source_counts(
    middle_payload: dict[str, Any],
) -> dict[str, int]:
    pages = extract_page_payloads(middle_payload)

    return {
        "pages": len(pages),
        "blocks": sum(
            len(page.get("para_blocks", []))
            for page in pages
            if isinstance(page.get("para_blocks"), list)
        ),
        "discarded_blocks": sum(
            len(page.get("discarded_blocks", []))
            for page in pages
            if isinstance(page.get("discarded_blocks"), list)
        ),
        "preproc_blocks": sum(
            len(page.get("preproc_blocks", []))
            for page in pages
            if isinstance(page.get("preproc_blocks"), list)
        ),
    }


def ir_counts(
    document: DocumentIR,
) -> dict[str, int]:
    return {
        "pages": len(document.pages),
        "blocks": sum(len(page.blocks) for page in document.pages),
        "discarded_blocks": sum(len(page.discarded_blocks) for page in document.pages),
        "lines": sum(len(block.lines) for block in iter_all_blocks(document)),
        "spans": sum(len(line.spans) for line in iter_lines(document)),
    }


def duplicate_summary(
    document: DocumentIR,
) -> dict[str, int]:
    content_fingerprints = [
        block_fingerprint(block) for block in iter_content_blocks(document)
    ]

    discarded_fingerprints = [
        block_fingerprint(block) for block in iter_discarded_blocks(document)
    ]

    content_counts = Counter(content_fingerprints)

    duplicated_content = sum(
        count - 1 for count in content_counts.values() if count > 1
    )

    overlap = len(set(content_fingerprints) & set(discarded_fingerprints))

    return {
        "duplicated_content_blocks": duplicated_content,
        "content_discarded_overlap": overlap,
    }


def collect_attribute_keys(
    document: DocumentIR,
) -> dict[str, Counter[str]]:
    counters: dict[str, Counter[str]] = {
        "document": Counter(document.attributes.keys()),
        "page": Counter(),
        "block": Counter(),
        "line": Counter(),
        "span": Counter(),
    }

    for page in document.pages:
        counters["page"].update(page.attributes.keys())

    for block in iter_all_blocks(document):
        counters["block"].update(block.attributes.keys())

    for line in iter_lines(document):
        counters["line"].update(line.attributes.keys())

    for span in iter_spans(document):
        counters["span"].update(span.attributes.keys())

    return counters


def collect_null_metrics(
    document: DocumentIR,
) -> dict[str, int]:
    blocks = list(iter_all_blocks(document))
    lines = list(iter_lines(document))
    spans = list(iter_spans(document))

    return {
        "blocks_without_type": sum(block.type is None for block in blocks),
        "blocks_without_bbox": sum(block.bbox is None for block in blocks),
        "lines_without_bbox": sum(line.bbox is None for line in lines),
        "spans_without_type": sum(span.type is None for span in spans),
        "text_spans_without_text": sum(
            span.type == "text" and not span.text for span in spans
        ),
    }


# %% [markdown]
# ## Resultado por documento


# %%
@dataclass(slots=True)
class ConversionResult:
    source_path: str
    source_size_bytes: int
    elapsed_seconds: float
    peak_memory_bytes: int
    source_counts: dict[str, int]
    ir_counts: dict[str, int]
    checks: dict[str, bool]
    duplicates: dict[str, int]
    null_metrics: dict[str, int]
    block_types: Counter[str]
    span_types: Counter[str]
    attribute_keys: dict[str, Counter[str]]
    serialized_size_bytes: int
    valid: bool
    error: str | None = None


def validate_one(
    middle_path: Path,
) -> tuple[DocumentIR | None, ConversionResult]:
    tracemalloc.start()
    started = time.perf_counter()

    try:
        document, middle_payload = build_document_ir(middle_path)

        serialized = document.model_dump_json(
            exclude_none=True,
        )

        restored = DocumentIR.model_validate_json(serialized)

        source = source_counts(middle_payload)
        target = ir_counts(document)
        duplicates = duplicate_summary(document)
        null_metrics = collect_null_metrics(document)

        checks = {
            "page_count_matches": (source["pages"] == target["pages"]),
            "block_count_matches": (source["blocks"] == target["blocks"]),
            "discarded_count_matches": (
                source["discarded_blocks"] == target["discarded_blocks"]
            ),
            "roundtrip_matches": restored == document,
            "serializable": bool(serialized),
            "preproc_not_serialized": ('"preproc_blocks"' not in serialized),
            "no_content_discarded_overlap": (
                duplicates["content_discarded_overlap"] == 0
            ),
        }

        elapsed = time.perf_counter() - started
        _, peak_memory = tracemalloc.get_traced_memory()

        result = ConversionResult(
            source_path=str(middle_path),
            source_size_bytes=middle_path.stat().st_size,
            elapsed_seconds=elapsed,
            peak_memory_bytes=peak_memory,
            source_counts=source,
            ir_counts=target,
            checks=checks,
            duplicates=duplicates,
            null_metrics=null_metrics,
            block_types=Counter(
                block.type or "<none>" for block in iter_all_blocks(document)
            ),
            span_types=Counter(span.type or "<none>" for span in iter_spans(document)),
            attribute_keys=collect_attribute_keys(document),
            serialized_size_bytes=len(serialized.encode("utf-8")),
            valid=all(checks.values()),
        )

        return document, result

    except Exception as exc:
        elapsed = time.perf_counter() - started
        _, peak_memory = tracemalloc.get_traced_memory()

        result = ConversionResult(
            source_path=str(middle_path),
            source_size_bytes=(
                middle_path.stat().st_size if middle_path.exists() else 0
            ),
            elapsed_seconds=elapsed,
            peak_memory_bytes=peak_memory,
            source_counts={},
            ir_counts={},
            checks={},
            duplicates={},
            null_metrics={},
            block_types=Counter(),
            span_types=Counter(),
            attribute_keys={
                "document": Counter(),
                "page": Counter(),
                "block": Counter(),
                "line": Counter(),
                "span": Counter(),
            },
            serialized_size_bytes=0,
            valid=False,
            error=f"{type(exc).__name__}: {exc}",
        )

        return None, result

    finally:
        tracemalloc.stop()


# %% [markdown]
# ## Persistência


# %%
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


def result_to_dict(
    result: ConversionResult,
) -> dict[str, Any]:
    return {
        "source_path": result.source_path,
        "source_size_bytes": result.source_size_bytes,
        "elapsed_seconds": result.elapsed_seconds,
        "peak_memory_bytes": result.peak_memory_bytes,
        "source_counts": result.source_counts,
        "ir_counts": result.ir_counts,
        "checks": result.checks,
        "duplicates": result.duplicates,
        "null_metrics": result.null_metrics,
        "block_types": dict(result.block_types),
        "span_types": dict(result.span_types),
        "attribute_keys": {
            level: dict(counter) for level, counter in result.attribute_keys.items()
        },
        "serialized_size_bytes": result.serialized_size_bytes,
        "valid": result.valid,
        "error": result.error,
    }


# %% [markdown]
# ## Descoberta dos arquivos

# %%
middle_paths = sorted(DATA_DIR.glob(MIDDLE_GLOB))

if MAX_DOCUMENTS is not None:
    middle_paths = middle_paths[:MAX_DOCUMENTS]

print(f"middle.json encontrados: {len(middle_paths)}")

for path in middle_paths[:10]:
    print(path)

if len(middle_paths) > 10:
    print(f"... e mais {len(middle_paths) - 10}")


# %% [markdown]
# ## Execução em lote

# %%
documents: list[DocumentIR] = []
results: list[ConversionResult] = []

batch_started = time.perf_counter()

for index, middle_path in enumerate(
    middle_paths,
    start=1,
):
    document, result = validate_one(middle_path)

    if document is not None:
        documents.append(document)

    results.append(result)

    status = "OK" if result.valid else "ERRO"

    print(
        f"[{index:03d}/{len(middle_paths):03d}] "
        f"{status} "
        f"{Path(result.source_path).name} "
        f"{result.elapsed_seconds:.3f}s"
    )

batch_elapsed = time.perf_counter() - batch_started


# %% [markdown]
# ## Agregação

# %%
valid_results = [result for result in results if result.valid]

invalid_results = [result for result in results if not result.valid]

block_type_counts: Counter[str] = Counter()
span_type_counts: Counter[str] = Counter()

attribute_key_counts: dict[str, Counter[str]] = {
    "document": Counter(),
    "page": Counter(),
    "block": Counter(),
    "line": Counter(),
    "span": Counter(),
}

null_metric_counts: Counter[str] = Counter()

for result in valid_results:
    block_type_counts.update(result.block_types)
    span_type_counts.update(result.span_types)
    null_metric_counts.update(result.null_metrics)

    for level, counter in result.attribute_keys.items():
        attribute_key_counts[level].update(counter)


# %% [markdown]
# ## Relatório consolidado

# %%
elapsed_values = [result.elapsed_seconds for result in valid_results]

peak_memory_values = [result.peak_memory_bytes for result in valid_results]

source_size_values = [result.source_size_bytes for result in valid_results]

serialized_size_values = [result.serialized_size_bytes for result in valid_results]

summary = {
    "documents": len(results),
    "valid_documents": len(valid_results),
    "invalid_documents": len(invalid_results),
    "batch_elapsed_seconds": batch_elapsed,
    "documents_per_second": (
        len(results) / batch_elapsed if batch_elapsed > 0 else None
    ),
    "pages": sum(result.ir_counts.get("pages", 0) for result in valid_results),
    "blocks": sum(result.ir_counts.get("blocks", 0) for result in valid_results),
    "discarded_blocks": sum(
        result.ir_counts.get("discarded_blocks", 0) for result in valid_results
    ),
    "lines": sum(result.ir_counts.get("lines", 0) for result in valid_results),
    "spans": sum(result.ir_counts.get("spans", 0) for result in valid_results),
    "source_preproc_blocks_ignored": sum(
        result.source_counts.get("preproc_blocks", 0) for result in valid_results
    ),
    "duplicated_content_blocks": sum(
        result.duplicates.get(
            "duplicated_content_blocks",
            0,
        )
        for result in valid_results
    ),
    "content_discarded_overlap": sum(
        result.duplicates.get(
            "content_discarded_overlap",
            0,
        )
        for result in valid_results
    ),
    "timing_seconds": {
        "mean": (statistics.mean(elapsed_values) if elapsed_values else None),
        "median": (statistics.median(elapsed_values) if elapsed_values else None),
        "p95": percentile(elapsed_values, 0.95),
        "max": max(elapsed_values) if elapsed_values else None,
    },
    "peak_memory_bytes": {
        "mean": (statistics.mean(peak_memory_values) if peak_memory_values else None),
        "median": (
            statistics.median(peak_memory_values) if peak_memory_values else None
        ),
        "p95": percentile(peak_memory_values, 0.95),
        "max": (max(peak_memory_values) if peak_memory_values else None),
    },
    "source_size_bytes": {
        "total": sum(source_size_values),
        "mean": (statistics.mean(source_size_values) if source_size_values else None),
        "max": (max(source_size_values) if source_size_values else None),
    },
    "serialized_ir_size_bytes": {
        "total": sum(serialized_size_values),
        "mean": (
            statistics.mean(serialized_size_values) if serialized_size_values else None
        ),
        "max": (max(serialized_size_values) if serialized_size_values else None),
    },
    "null_metrics": dict(null_metric_counts),
}


# %% [markdown]
# ## Relatórios de schema observado

# %%
observed_schema = {
    "block_types": dict(block_type_counts.most_common()),
    "span_types": dict(span_type_counts.most_common()),
    "attribute_keys": {
        level: dict(counter.most_common())
        for level, counter in attribute_key_counts.items()
    },
}


# %% [markdown]
# ## Documentos mais lentos e maiores

# %%
slowest_documents = [
    {
        "source_path": result.source_path,
        "elapsed_seconds": result.elapsed_seconds,
        "source_size_bytes": result.source_size_bytes,
        "pages": result.ir_counts.get("pages"),
        "blocks": result.ir_counts.get("blocks"),
        "spans": result.ir_counts.get("spans"),
    }
    for result in sorted(
        valid_results,
        key=lambda item: item.elapsed_seconds,
        reverse=True,
    )[:20]
]

largest_documents = [
    {
        "source_path": result.source_path,
        "source_size_bytes": result.source_size_bytes,
        "serialized_size_bytes": result.serialized_size_bytes,
        "pages": result.ir_counts.get("pages"),
        "blocks": result.ir_counts.get("blocks"),
        "spans": result.ir_counts.get("spans"),
    }
    for result in sorted(
        valid_results,
        key=lambda item: item.source_size_bytes,
        reverse=True,
    )[:20]
]


# %% [markdown]
# ## Persistência dos relatórios

# %%
write_json(
    summary,
    OUTPUT_DIR / "summary.json",
)

write_json(
    observed_schema,
    OUTPUT_DIR / "observed_schema.json",
)

write_json(
    [result_to_dict(result) for result in results],
    OUTPUT_DIR / "validation_report.json",
)

write_json(
    [result_to_dict(result) for result in invalid_results],
    OUTPUT_DIR / "invalid_documents.json",
)

write_json(
    slowest_documents,
    OUTPUT_DIR / "slowest_documents.json",
)

write_json(
    largest_documents,
    OUTPUT_DIR / "largest_documents.json",
)

summary


# %% [markdown]
# ## Schema observado

# %%
observed_schema


# %% [markdown]
# ## Falhas

# %%
if invalid_results:
    for result in invalid_results:
        print(
            result.source_path,
            result.error,
            result.checks,
        )
else:
    print("Nenhum documento inválido.")


# %% [markdown]
# ## Critério de regressão

# %%
regression_checks = {
    "all_documents_valid": (len(invalid_results) == 0),
    "all_source_blocks_preserved": all(
        result.checks.get(
            "block_count_matches",
            False,
        )
        for result in valid_results
    ),
    "all_discarded_blocks_preserved": all(
        result.checks.get(
            "discarded_count_matches",
            False,
        )
        for result in valid_results
    ),
    "all_roundtrips_valid": all(
        result.checks.get(
            "roundtrip_matches",
            False,
        )
        for result in valid_results
    ),
    "no_preproc_serialized": all(
        result.checks.get(
            "preproc_not_serialized",
            False,
        )
        for result in valid_results
    ),
    "no_content_discarded_overlap": all(
        result.checks.get(
            "no_content_discarded_overlap",
            False,
        )
        for result in valid_results
    ),
}

write_json(
    regression_checks,
    OUTPUT_DIR / "regression_checks.json",
)

regression_checks


# %% [markdown]
# ## Falhar explicitamente em regressão

# %%
if FAIL_ON_INVALID and not all(regression_checks.values()):
    raise AssertionError(
        json.dumps(
            {
                "regression_checks": regression_checks,
                "invalid_documents": [
                    result_to_dict(result) for result in invalid_results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

print("Validação em lote concluída.")
