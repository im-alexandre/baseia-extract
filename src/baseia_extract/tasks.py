from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import mineru
from .runpod import managed_mineru_pods


def extract() -> dict[str, Any]:
    """Executa a extração completa com pods RunPod temporários e gerenciados."""
    original_settings = mineru.settings

    with managed_mineru_pods() as pods:
        mineru.settings = replace(
            original_settings,
            mineru_api_urls=tuple(pod.api_url for pod in pods),
        )
        try:
            return mineru.extract()
        finally:
            mineru.settings = original_settings
