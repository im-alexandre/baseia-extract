"""Lista revisões pendentes presentes nos metadados canônicos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .inventory_selection import select_inventory_rows
from .layout import document_layout
from .settings import settings

_COLUMNS = [
    "path",
    "relative_path",
    "document_id",
    "attribute",
    "candidate",
    "status",
    "reason",
    "provenance",
]


def _source_path(inventory_path: str | Path | None) -> Path:
    if inventory_path is not None and str(inventory_path).strip():
        return Path(inventory_path).expanduser().resolve()
    return settings.inventory_path


def _review_items(
    row: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    document_path: Path,
) -> list[dict[str, Any]]:
    attributes = metadata.get("attributes")
    if not isinstance(attributes, Mapping):
        return []
    reviews = attributes.get("review")
    if not isinstance(reviews, Mapping):
        return []

    items: list[dict[str, Any]] = []
    for attribute, review in reviews.items():
        if not isinstance(review, Mapping) or review.get("required") is not True:
            continue
        attribute_name = str(attribute)
        items.append(
            {
                "path": str(document_path),
                "relative_path": str(
                    row.get("collection_relative_path")
                    or row.get("relative_path")
                    or ""
                ),
                "document_id": str(row.get("document_id") or ""),
                "attribute": attribute_name,
                "candidate": review.get(
                    "candidate", metadata.get(attribute_name)
                ),
                "status": review.get("status"),
                "reason": review.get("reason"),
                "provenance": review.get("provenance"),
            }
        )
    return items


def _table_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def review(
    inventory_path: str | Path | None = None,
    collection: str = "",
    collection_path: str = "",
    output_format: str = "table",
) -> dict[str, Any]:
    """Lista revisões requeridas sem alterar inventário ou artefatos."""
    normalized_format = output_format.strip().casefold() or "table"
    if normalized_format not in {"table", "json"}:
        raise ValueError("Formato inválido. Use table ou json.")
    source_path = _source_path(inventory_path)
    rows = select_inventory_rows(
        source_path,
        collection=collection,
        collection_path=collection_path,
    )

    items: list[dict[str, Any]] = []
    missing_metadata = 0
    for row in rows:
        layout = document_layout(row)
        metadata_path = layout.metadata_path
        if not metadata_path.is_file():
            missing_metadata += 1
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"metadata.json inválido: {metadata_path}"
            ) from error
        if not isinstance(metadata, Mapping):
            raise ValueError(f"metadata.json sem objeto raiz: {metadata_path}")
        items.extend(
            _review_items(
                row,
                metadata,
                document_path=layout.pdf_path,
            )
        )

    items.sort(
        key=lambda item: (
            item["path"],
            item["relative_path"],
            item["document_id"],
            item["attribute"],
        )
    )
    result = {
        "inventory_path": str(source_path),
        "selected_documents": len(rows),
        "missing_metadata": missing_metadata,
        "items": items,
    }
    if normalized_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        frame = pd.DataFrame(items, columns=_COLUMNS)
        if not frame.empty:
            for column in ("candidate", "provenance"):
                frame[column] = frame[column].map(_table_value)
            print(frame.to_string(index=False))
        else:
            print("Nenhuma revisão obrigatória encontrada.")
        print(
            f"Documentos selecionados: {len(rows)}; "
            f"revisões obrigatórias: {len(items)}; "
            f"metadata.json ausentes: {missing_metadata}"
        )
    return result


__all__ = ["review"]
