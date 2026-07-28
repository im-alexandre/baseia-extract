from __future__ import annotations

from pathlib import Path
from typing import Any

from . import mineru
from .audit import audit, audit_inventory
from .runpod import managed_mineru_pods


def extract() -> dict[str, Any]:
    """
    Audita o inventário, cria pods temporários, extrai e audita a saída.

    A auditoria final roda depois que o contexto do RunPod encerra os pods.
    """
    inventory_summary = audit_inventory()
    manifest_path = Path(inventory_summary["extraction_manifest_path"])

    extraction_summary: dict[str, Any] | None = None
    try:
        with managed_mineru_pods() as pods:
            extraction_summary = mineru.extract(
                api_urls=tuple(pod.api_url for pod in pods),
                manifest_path=manifest_path,
            )
    finally:
        audit_summary = audit()

    return {
        "extraction": extraction_summary,
        "audit": audit_summary,
    }
