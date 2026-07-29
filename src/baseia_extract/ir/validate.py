"""Validações estruturais do IR, sem enriquecer ou reescrever conteúdo."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .builder import _page_payloads
from .models import BlockIR, DocumentIR


def _nested_source_blocks(block: dict[str, Any]) -> Iterable[dict[str, Any]]:
    children = block.get("blocks")
    if children is None:
        return
    if not isinstance(children, list):
        raise TypeError("blocks aninhado deve ser uma lista.")
    for child in children:
        if not isinstance(child, dict):
            raise TypeError("blocks aninhado deve conter apenas objetos.")
        yield child
        yield from _nested_source_blocks(child)


def _all_source_blocks(blocks: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for block in blocks:
        yield block
        yield from _nested_source_blocks(block)


def _source_counts(payload: dict[str, Any]) -> dict[str, int]:
    pages = _page_payloads(payload)
    content_roots = [block for page in pages for block in page.get("para_blocks", []) if isinstance(block, dict)]
    discarded_roots = [block for page in pages for block in page.get("discarded_blocks", []) if isinstance(block, dict)]
    content_nodes = list(_all_source_blocks(content_roots))
    discarded_nodes = list(_all_source_blocks(discarded_roots))
    return {"pages": len(pages), "blocks": len(content_roots), "discarded_blocks": len(discarded_roots), "nested_blocks": (len(content_nodes) - len(content_roots)) + (len(discarded_nodes) - len(discarded_roots)), "block_nodes": len(content_nodes) + len(discarded_nodes), "lines": sum(len(block.get("lines", [])) for block in (*content_nodes, *discarded_nodes) if isinstance(block.get("lines"), list)), "spans": sum(len(line.get("spans", [])) for block in (*content_nodes, *discarded_nodes) if isinstance(block.get("lines"), list) for line in block["lines"] if isinstance(line, dict) and isinstance(line.get("spans"), list)), "preproc_blocks": sum(len(page.get("preproc_blocks", [])) for page in pages if isinstance(page.get("preproc_blocks"), list))}


def _nested_ir_blocks(block: BlockIR) -> Iterable[BlockIR]:
    for child in block.blocks:
        yield child
        yield from _nested_ir_blocks(child)


def _all_ir_blocks(blocks: Iterable[BlockIR]) -> Iterable[BlockIR]:
    for block in blocks:
        yield block
        yield from _nested_ir_blocks(block)


def _ir_counts(document: DocumentIR) -> dict[str, int]:
    content_roots = [block for page in document.pages for block in page.blocks]
    discarded_roots = [block for page in document.pages for block in page.discarded_blocks]
    nodes = list(_all_ir_blocks((*content_roots, *discarded_roots)))
    return {"pages": len(document.pages), "blocks": len(content_roots), "discarded_blocks": len(discarded_roots), "nested_blocks": len(nodes) - len(content_roots) - len(discarded_roots), "block_nodes": len(nodes), "lines": sum(len(block.lines) for block in nodes), "spans": sum(len(line.spans) for block in nodes for line in block.lines)}


def _block_fingerprint(block: BlockIR) -> str:
    payload = block.model_dump(mode="json", exclude={"id", "block_index", "attributes"}, exclude_none=True)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _duplicates(document: DocumentIR) -> dict[str, int]:
    content = [_block_fingerprint(block) for page in document.pages for block in page.blocks]
    discarded = [_block_fingerprint(block) for page in document.pages for block in page.discarded_blocks]
    counts = Counter(content)
    return {"duplicated_content_blocks": sum(count - 1 for count in counts.values() if count > 1), "content_discarded_overlap": len(set(content) & set(discarded))}


def validate_document_ir(document: DocumentIR, middle_path: str | Path | None = None) -> dict[str, Any]:
    """Retorna invariantes de perda, round-trip e separação de preproc.

    Quando ``middle_path`` não é informado, utiliza o caminho registrado no
    documento. Nenhum arquivo é alterado.
    """
    path = Path(middle_path) if middle_path is not None else Path(document.source_path)
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise TypeError(f"Raiz inválida em {path}: esperado objeto JSON.")
    source_counts = _source_counts(payload)
    ir_counts = _ir_counts(document)
    serialized = document.model_dump_json(exclude_none=True)
    restored = DocumentIR.model_validate_json(serialized)
    checks = {"middle_sha256_matches": hashlib.sha256(path.read_bytes()).hexdigest() == document.middle_sha256, "page_count_matches": source_counts["pages"] == ir_counts["pages"], "block_count_matches": source_counts["blocks"] == ir_counts["blocks"], "discarded_count_matches": source_counts["discarded_blocks"] == ir_counts["discarded_blocks"], "nested_block_count_matches": source_counts["nested_blocks"] == ir_counts["nested_blocks"], "block_node_count_matches": source_counts["block_nodes"] == ir_counts["block_nodes"], "line_count_matches": source_counts["lines"] == ir_counts["lines"], "span_count_matches": source_counts["spans"] == ir_counts["spans"], "roundtrip_matches": restored == document, "serializable": bool(serialized), "preproc_not_serialized": '"preproc_blocks"' not in serialized}
    return {"source_path": str(path), "source_counts": source_counts, "ir_counts": ir_counts, "checks": checks, "duplicates": _duplicates(document), "valid": all(checks.values())}
