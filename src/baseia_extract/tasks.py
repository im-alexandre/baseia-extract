from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from . import mineru
from .runpod import managed_mineru_pods


def extract(
    manifest: str | Path | None = None,
    output: str | Path | None = None,
    workers_per_pod: int | None = None,
    retries: int | None = None,
    overwrite: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Executa a extração MinerU com pods RunPod temporários e gerenciados."""
    original_settings = mineru.settings

    with managed_mineru_pods() as pods:
        mineru.settings = replace(
            original_settings,
            mineru_api_urls=tuple(pod.api_url for pod in pods),
        )
        try:
            return mineru.extract(
                manifest=manifest,
                output=output,
                workers_per_pod=workers_per_pod,
                retries=retries,
                overwrite=overwrite,
                limit=limit,
            )
        finally:
            mineru.settings = original_settings
