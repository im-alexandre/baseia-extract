"""Seleção segura de registros de um inventário materializado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .identity import collection_slug

REQUIRED_COLUMNS = {
    "collection",
    "collection_slug",
    "collection_relative_path",
    "document_id",
    "revision_id",
    "relative_path",
    "status",
    "sha256",
}


def physical_path_mask(
    values: pd.Series,
    collection_path: str | Path,
) -> pd.Series:
    """Marca paths físicos situados sob um diretório ou iguais a um PDF."""
    root = Path(collection_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path da coleção ausente: {root}")

    def selected_by_path(value: object) -> bool:
        raw_value = str(value or "").strip()
        if not raw_value:
            return False
        candidate = Path(raw_value).expanduser().resolve()
        if root.is_file():
            return candidate == root
        return candidate.is_relative_to(root)

    return values.map(selected_by_path)


def select_inventory_rows(
    inventory_path: str | Path,
    *,
    collection: str = "",
    collection_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Seleciona documentos válidos por identidade ou raiz física.

    O path funciona apenas como seletor sobre o inventário existente. Ele não
    recria identidades, revisões nem executa a etapa de inventário.
    """
    source = Path(inventory_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Inventário ausente: {source}")
    inventory = pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
    )
    missing = REQUIRED_COLUMNS - set(inventory.columns)
    if missing:
        raise ValueError(
            f"Inventário sem colunas obrigatórias: {sorted(missing)}"
        )

    raw_collection_path = (
        str(collection_path).strip()
        if collection_path is not None
        else ""
    )
    if collection.strip() and raw_collection_path:
        raise ValueError(
            "Use somente um seletor: --collection ou --path."
        )

    selected = inventory.loc[inventory["status"].eq("ok")].copy()
    if collection.strip():
        selector = collection.strip()
        selector_slug = collection_slug(selector)
        selected = selected.loc[
            selected["collection"].str.casefold().eq(selector.casefold())
            | selected["collection_slug"].eq(selector_slug)
        ]
    elif raw_collection_path:
        if "path" not in inventory.columns:
            raise ValueError(
                "O seletor --path exige a coluna path no inventário."
            )
        selected = selected.loc[
            physical_path_mask(
                selected["path"],
                raw_collection_path,
            )
        ]

    if selected.empty:
        raise ValueError(
            "Nenhum documento válido corresponde à seleção informada."
        )
    return selected.to_dict("records")


__all__ = [
    "REQUIRED_COLUMNS",
    "physical_path_mask",
    "select_inventory_rows",
]
