"""Construção determinística do IR canônico a partir do MinerU."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .models import BlockIR, DocumentIR, LineIR, PageIR, SpanIR

ROOT_FIELDS = frozenset({"pdf_info", "pages", "page_info", "para_blocks", "discarded_blocks", "preproc_blocks", "_backend", "_version_name"})
PAGE_FIELDS = frozenset({"page", "page_idx", "page_no", "page_number", "width", "height", "page_size", "para_blocks", "discarded_blocks", "preproc_blocks"})
BLOCK_FIELDS = frozenset({"type", "block_type", "index", "text", "content", "bbox", "score", "level", "cross_page", "image_path", "latex", "html", "lines", "blocks"})
LINE_FIELDS = frozenset({"bbox", "score", "spans"})
SPAN_FIELDS = frozenset({"type", "text", "content", "bbox", "score", "latex", "html", "image_path"})


def _unknown_attributes(payload: dict[str, Any], known_fields: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in known_fields}


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes"}:
            return True
        if value.lower() in {"false", "0", "no"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _as_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _child_id(parent_id: str, kind: str, index: int) -> str:
    return f"{parent_id}:{kind}{index:04d}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_items(value: Any, *, location: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{location} deve ser uma lista, recebido {type(value).__name__}.")
    if invalid := [index for index, item in enumerate(value) if not isinstance(item, dict)]:
        raise TypeError(f"{location} contém item não-objeto nos índices {invalid}.")
    return value


def _page_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("pdf_info", "pages", "page_info"):
        if key in payload and isinstance(payload[key], list):
            return _object_items(payload[key], location=key)
    if any(key in payload for key in ("para_blocks", "discarded_blocks", "preproc_blocks")):
        return [payload]
    raise ValueError("Não foi possível localizar as páginas no middle.json.")


def _page_size(payload: dict[str, Any]) -> tuple[float | None, float | None]:
    width, height = _as_float(payload.get("width")), _as_float(payload.get("height"))
    size = payload.get("page_size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        width = width if width is not None else _as_float(size[0])
        height = height if height is not None else _as_float(size[1])
    return width, height


def _build_span(payload: dict[str, Any], *, span_id: str) -> SpanIR:
    return SpanIR(id=span_id, type=_optional_string(payload, "type"), text=_optional_string(payload, "text"), content=_optional_string(payload, "content"), bbox=_as_bbox(payload.get("bbox")), score=_as_float(payload.get("score")), latex=_optional_string(payload, "latex"), html=_optional_string(payload, "html"), image_path=_optional_string(payload, "image_path"), attributes=_unknown_attributes(payload, SPAN_FIELDS))


def _build_line(payload: dict[str, Any], *, line_id: str) -> LineIR:
    spans = _object_items(payload.get("spans"), location=f"{line_id}.spans")
    return LineIR(id=line_id, bbox=_as_bbox(payload.get("bbox")), score=_as_float(payload.get("score")), spans=[_build_span(item, span_id=_child_id(line_id, "s", index)) for index, item in enumerate(spans)], attributes=_unknown_attributes(payload, LINE_FIELDS))


def _build_block(payload: dict[str, Any], *, block_id: str, fallback_index: int) -> BlockIR:
    lines = _object_items(payload.get("lines"), location=f"{block_id}.lines")
    blocks = _object_items(payload.get("blocks"), location=f"{block_id}.blocks")
    return BlockIR(id=block_id, block_index=_as_int(payload.get("index")) if "index" in payload else fallback_index, type=_first_present(payload, "type", "block_type") if isinstance(_first_present(payload, "type", "block_type"), str) else None, text=_optional_string(payload, "text"), content=_optional_string(payload, "content"), bbox=_as_bbox(payload.get("bbox")), score=_as_float(payload.get("score")), level=_as_int(payload.get("level")), cross_page=_as_bool(payload.get("cross_page")), image_path=_optional_string(payload, "image_path"), latex=_optional_string(payload, "latex"), html=_optional_string(payload, "html"), lines=[_build_line(item, line_id=_child_id(block_id, "l", index)) for index, item in enumerate(lines)], blocks=[_build_block(item, block_id=_child_id(block_id, "b", index), fallback_index=index) for index, item in enumerate(blocks)], attributes=_unknown_attributes(payload, BLOCK_FIELDS))


def _build_page(payload: dict[str, Any], *, page_id: str, fallback_index: int) -> PageIR:
    blocks = _object_items(payload.get("para_blocks"), location=f"{page_id}.para_blocks")
    discarded = _object_items(payload.get("discarded_blocks"), location=f"{page_id}.discarded_blocks")
    width, height = _page_size(payload)
    page = _as_int(_first_present(payload, "page", "page_idx", "page_no", "page_number"))
    return PageIR(id=page_id, page=fallback_index if page is None else page, width=width, height=height, blocks=[_build_block(item, block_id=_child_id(page_id, "b", index), fallback_index=index) for index, item in enumerate(blocks)], discarded_blocks=[_build_block(item, block_id=_child_id(page_id, "d", index), fallback_index=index) for index, item in enumerate(discarded)], attributes=_unknown_attributes(payload, PAGE_FIELDS))


def build_document_ir(middle_path: str | Path, *, source_document_id: str | None = None, source_pdf_sha256: str | None = None) -> DocumentIR:
    """Lê um ``middle.json`` e produz IR sem normalizar qualquer texto.

    ``para_blocks`` é o único conteúdo canônico. ``discarded_blocks`` é
    preservado separadamente e ``preproc_blocks`` não é serializado.
    """
    path = Path(middle_path)
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise TypeError(f"Raiz inválida em {path}: esperado objeto JSON.")
    middle_sha256 = _sha256_file(path)
    # O ID fornecido pelo inventário já é a identidade canônica do documento.
    # Reaplicar SHA-256 aqui criava uma segunda identidade e quebrava o
    # pareamento diretório/inventário -> IR -> estrutura.
    document_id = source_document_id or (source_pdf_sha256 or middle_sha256)[:16]
    pages = _page_payloads(payload)
    return DocumentIR(id=document_id, source_path=str(path), source_name=path.stem.removesuffix("_middle"), middle_sha256=middle_sha256, source_document_id=source_document_id, source_pdf_sha256=source_pdf_sha256, backend=_optional_string(payload, "_backend"), backend_version=_optional_string(payload, "_version_name"), pages=[_build_page(item, page_id=_child_id(document_id, "p", index), fallback_index=index) for index, item in enumerate(pages)], attributes=_unknown_attributes(payload, ROOT_FIELDS))


def build_document_ir_batch(middle_paths: Iterable[str | Path], *, source_document_ids: Sequence[str | None] | None = None, source_pdf_sha256s: Sequence[str | None] | None = None) -> list[DocumentIR]:
    """Constrói documentos em ordem, sem I/O adicional, persistência ou estado global."""
    paths = list(middle_paths)
    if source_document_ids is not None and len(source_document_ids) != len(paths):
        raise ValueError("source_document_ids deve ter o mesmo tamanho de middle_paths.")
    if source_pdf_sha256s is not None and len(source_pdf_sha256s) != len(paths):
        raise ValueError("source_pdf_sha256s deve ter o mesmo tamanho de middle_paths.")
    return [build_document_ir(path, source_document_id=None if source_document_ids is None else source_document_ids[index], source_pdf_sha256=None if source_pdf_sha256s is None else source_pdf_sha256s[index]) for index, path in enumerate(paths)]
