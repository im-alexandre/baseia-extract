"""Reconciliação não destrutiva do ``content_list_v2`` com o DocumentIR.

O ``DocumentIR`` continua sendo a evidência física canônica. O v2 acrescenta
uma proposta de tipo e ordem de leitura, ligada aos blocos existentes sem
copiar o conteúdo textual para a estrutura semântica.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .ir.models import BlockIR, DocumentIR, PageIR

RECONCILER_VERSION = 2

TYPE_COMPATIBILITY: dict[str, frozenset[str]] = {
    "algorithm": frozenset({"algorithm", "code"}),
    "chart": frozenset({"chart", "image"}),
    "code": frozenset({"code"}),
    "equation_interline": frozenset(
        {"interline_equation", "equation"}
    ),
    "image": frozenset({"image"}),
    "index": frozenset({"index", "list"}),
    "list": frozenset({"list", "index"}),
    "page_aside_text": frozenset({"aside_text"}),
    "page_footer": frozenset({"footer"}),
    "page_footnote": frozenset({"page_footnote"}),
    "page_header": frozenset({"header"}),
    "page_number": frozenset({"page_number"}),
    "paragraph": frozenset(
        {"text", "paragraph", "abstract", "ref_text"}
    ),
    "table": frozenset({"table"}),
    "title": frozenset({"title"}),
}

_NON_CONTENT_KEYS = frozenset(
    {
        "attribute",
        "bbox",
        "image_path",
        "image_source",
        "item_type",
        "level",
        "list_type",
        "path",
        "score",
        "type",
    }
)


def _content_strings(value: Any, *, key: str = "") -> list[str]:
    if isinstance(value, str):
        return [value] if key == "content" else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_content_strings(item, key=key))
        return result
    if isinstance(value, dict):
        result = []
        for child_key, item in value.items():
            if child_key not in _NON_CONTENT_KEYS:
                result.extend(_content_strings(item, key=child_key))
        return result
    return []


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _block_text(block: BlockIR) -> str:
    values: list[str] = []
    for candidate in (block.text, block.content, block.html, block.latex):
        if candidate:
            values.append(candidate)
    for line in block.lines:
        for span in line.spans:
            for candidate in (
                span.text,
                span.content,
                span.html,
                span.latex,
            ):
                if candidate:
                    values.append(candidate)
                    break
    for child in block.blocks:
        child_text = _block_text(child)
        if child_text:
            values.append(child_text)
    return _normalize_text(" ".join(values))


def _bbox_candidates(
    value: Any,
    page: PageIR,
) -> list[tuple[str, list[float]]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return []
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return []
    if (
        not all(math.isfinite(item) for item in bbox)
        or min(bbox) < 0
        or bbox[0] > bbox[2]
        or bbox[1] > bbox[3]
    ):
        return []
    candidates = [("page_units", bbox)]
    if (
        page.width is not None
        and page.height is not None
        and max(bbox) <= 1000
    ):
        scale_x = page.width / 1000.0
        scale_y = page.height / 1000.0
        scaled = [
            bbox[0] * scale_x,
            bbox[1] * scale_y,
            bbox[2] * scale_x,
            bbox[3] * scale_y,
        ]
        if scaled != bbox:
            candidates.append(("normalized_0_1000", scaled))
    return candidates


def _iou(left: list[float] | None, right: list[float] | None) -> float:
    if left is None or right is None:
        return 0.0
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(
        0.0, left[3] - left[1]
    )
    right_area = max(0.0, right[2] - right[0]) * max(
        0.0, right[3] - right[1]
    )
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def load_content_list_v2(path: str | Path) -> dict[str, Any]:
    """Carrega o v2 e devolve itens lineares sem paths locais publicados."""
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise TypeError("content_list_v2 deve ter uma lista na raiz.")

    items: list[dict[str, Any]] = []
    global_order = 0
    invalid_pages: list[int] = []
    for page_index, page_items in enumerate(raw):
        if not isinstance(page_items, list):
            invalid_pages.append(page_index)
            continue
        for ordinal, item in enumerate(page_items):
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            content_mapping = content if isinstance(content, dict) else {}
            text_parts = _content_strings(content_mapping)
            items.append(
                {
                    "item_id": (
                        f"content-list-v2:p{page_index:04d}:"
                        f"i{ordinal:04d}"
                    ),
                    "page_index": page_index,
                    "ordinal": ordinal,
                    "global_order": global_order,
                    "type": (
                        str(item["type"])
                        if isinstance(item.get("type"), str)
                        else None
                    ),
                    "bbox": item.get("bbox"),
                    "text": " ".join(text_parts).strip(),
                    "text_parts": text_parts,
                    "level": (
                        int(content_mapping["level"])
                        if (
                            isinstance(content_mapping.get("level"), int)
                            and not isinstance(
                                content_mapping.get("level"),
                                bool,
                            )
                        )
                        else None
                    ),
                }
            )
            global_order += 1
    return {
        "source": {
            "filename": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "page_count": len(raw),
            "item_count": len(items),
            "invalid_page_indices": invalid_pages,
        },
        "items": items,
    }


def _confidence_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def reconcile_content_list_v2(
    document: DocumentIR,
    path: str | Path,
) -> dict[str, Any]:
    """Associa itens do v2 a blocos IR da mesma página, um para um.

    A geometria domina o score porque o MinerU normaliza o bbox do v2 para uma
    grade 0–1000. Texto e tipo servem para confirmar e desempatar.
    """
    loaded = load_content_list_v2(path)
    items = loaded["items"]
    used: set[str] = set()
    matches: list[dict[str, Any]] = []
    unmatched_items: list[dict[str, Any]] = []
    block_locations: dict[str, dict[str, Any]] = {}
    for page_index, page in enumerate(document.pages):
        for physical_order, block in enumerate(page.blocks):
            block_locations[block.id] = {
                "page_index": page_index,
                "physical_order": physical_order,
                "source_kind": "content",
            }
        for physical_order, block in enumerate(page.discarded_blocks):
            block_locations[block.id] = {
                "page_index": page_index,
                "physical_order": physical_order,
                "source_kind": "discarded",
            }

    for item in items:
        page_index = int(item["page_index"])
        page = (
            document.pages[page_index]
            if 0 <= page_index < len(document.pages)
            else None
        )
        candidates: list[
            tuple[float, float, float, bool, BlockIR, str, str]
        ] = []
        if page is not None:
            bbox_candidates = _bbox_candidates(item.get("bbox"), page)
            for source_kind, blocks in (
                ("content", page.blocks),
                ("discarded", page.discarded_blocks),
            ):
                for block in blocks:
                    if block.id in used:
                        continue
                    bbox_space, geometry = max(
                        (
                            (space, _iou(candidate_bbox, block.bbox))
                            for space, candidate_bbox in bbox_candidates
                        ),
                        key=lambda candidate: candidate[1],
                        default=("unavailable", 0.0),
                    )
                    source_text = _normalize_text(str(item.get("text") or ""))
                    target_text = _block_text(block)
                    text_similarity = (
                        SequenceMatcher(
                            None,
                            source_text,
                            target_text,
                        ).ratio()
                        if source_text and target_text
                        else 0.0
                    )
                    compatible = block.type in TYPE_COMPATIBILITY.get(
                        str(item.get("type")),
                        frozenset(),
                    )
                    score = (
                        0.55 * geometry
                        + 0.35 * text_similarity
                        + (0.10 if compatible else 0.0)
                    )
                    candidates.append(
                        (
                            score,
                            geometry,
                            text_similarity,
                            compatible,
                            block,
                            source_kind,
                            bbox_space,
                        )
                    )
        candidates.sort(
            key=lambda candidate: (
                -candidate[0],
                -candidate[1],
                -candidate[2],
                candidate[4].id,
            )
        )
        best = candidates[0] if candidates else None
        if best is None or best[0] < 0.35:
            unmatched_items.append(
                {
                    "item_id": item["item_id"],
                    "page_index": page_index,
                    "ordinal": item["ordinal"],
                    "global_order": item["global_order"],
                    "source_type": item.get("type"),
                    "bbox": item.get("bbox"),
                    "text_sha256": hashlib.sha256(
                        str(item.get("text") or "").encode("utf-8")
                    ).hexdigest(),
                }
            )
            continue

        (
            score,
            geometry,
            text_similarity,
            compatible,
            block,
            source_kind,
            bbox_space,
        ) = best
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        score_margin = score - second_score
        ambiguous = bool(
            len(candidates) > 1
            and score_margin < 0.05
            and candidates[1][1] >= 0.5
        )
        used.add(block.id)
        divergences: list[str] = []
        if not compatible:
            divergences.append("type_mismatch")
        if geometry < 0.8:
            divergences.append("bbox_iou_below_0_8")
        if item.get("text") and text_similarity < 0.8:
            divergences.append("text_similarity_below_0_8")
        if ambiguous:
            divergences.append("ambiguous_candidate")
        usable_for_structure = bool(
            not ambiguous
            and (
                score >= 0.65
                or (geometry >= 0.8 and compatible)
            )
        )
        matches.append(
            {
                "block_id": block.id,
                "item_id": item["item_id"],
                "page_index": page_index,
                "ordinal": item["ordinal"],
                "global_order": item["global_order"],
                "source_kind": source_kind,
                "source_type": item.get("type"),
                "level": item.get("level"),
                "confidence": round(score, 6),
                "confidence_label": _confidence_label(score),
                "score_margin": round(score_margin, 6),
                "ambiguous": ambiguous,
                "usable_for_structure": usable_for_structure,
                "bbox_coordinate_space": bbox_space,
                "bbox_iou": round(geometry, 6),
                "text_similarity": round(text_similarity, 6),
                "compatible_type": compatible,
                "divergences": divergences,
            }
        )

    unmatched_blocks = [
        {
            "block_id": block_id,
            **location,
        }
        for block_id, location in block_locations.items()
        if block_id not in used
    ]
    match_scores = [float(item["confidence"]) for item in matches]
    source = dict(loaded["source"])
    return {
        "schema_version": 1,
        "reconciler_version": RECONCILER_VERSION,
        "source": source,
        "page_count_matches_ir": (
            int(source["page_count"]) == len(document.pages)
        ),
        "matches": matches,
        "unmatched_items": unmatched_items,
        "unmatched_blocks": unmatched_blocks,
        "counts": {
            "matched": len(matches),
            "matched_content": sum(
                item["source_kind"] == "content" for item in matches
            ),
            "matched_discarded": sum(
                item["source_kind"] == "discarded" for item in matches
            ),
            "unmatched_items": len(unmatched_items),
            "unmatched_blocks": len(unmatched_blocks),
            "pages_ir": len(document.pages),
            "usable_for_structure": sum(
                item["usable_for_structure"] for item in matches
            ),
            "ambiguous": sum(item["ambiguous"] for item in matches),
        },
        "confidence": {
            "minimum": min(match_scores, default=0.0),
            "mean": (
                round(sum(match_scores) / len(match_scores), 6)
                if match_scores
                else 0.0
            ),
            "high": sum(
                item["confidence_label"] == "high" for item in matches
            ),
            "medium": sum(
                item["confidence_label"] == "medium" for item in matches
            ),
            "low": sum(
                item["confidence_label"] == "low" for item in matches
            ),
        },
    }


__all__ = [
    "RECONCILER_VERSION",
    "load_content_list_v2",
    "reconcile_content_list_v2",
]
