from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable

from mineru_client import MineruClient

from . import mineru
from .audit import audit_inventory
from .object_storage import ObjectStorage
from .reporting import reporter
from .runpod import (
    PodCoordinator,
    managed_mineru_pods,
    pod_resource_usage,
)
from .settings import settings


def _monitor_pod_commands(
    coordinator: PodCoordinator,
    endpoint_registry: mineru.ApiEndpointRegistry,
    command_dir: Path,
    monitor_stop: threading.Event,
    graceful_stop: threading.Event,
) -> None:
    processed_dir = command_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    while not monitor_stop.is_set():
        for command_path in sorted(command_dir.glob("*.json")):
            try:
                payload = json.loads(
                    command_path.read_text(encoding="utf-8")
                )
                action = payload.get("action")
                if action == "stop":
                    graceful_stop.set()
                    reporter.request_stop()
                    command_path.replace(
                        processed_dir / command_path.name
                    )
                    continue
                if action == "scale":
                    workers = int(payload["workers"])
                    updated = endpoint_registry.set_all_capacities(workers)
                    reporter.event(
                        "Capacidade geral atualizada em runtime | "
                        f"pods={updated} | workers={workers}",
                        color="cyan",
                    )
                    command_path.replace(
                        processed_dir / command_path.name
                    )
                    continue
                pods = payload.get("pods", [])
                if not isinstance(pods, list):
                    raise TypeError("Campo pods deve ser uma lista.")
                workers_value = payload.get("workers")
                workers = (
                    int(workers_value)
                    if workers_value is not None
                    else None
                )
                if workers is not None and workers < 1:
                    raise ValueError("workers deve ser maior que zero.")
                for pod in pods:
                    added = coordinator.add_pod_spec(str(pod), workers)
                    if (
                        not added
                        and workers is not None
                        and endpoint_registry.set_initial_capacity(
                            str(pod),
                            workers,
                        )
                    ):
                        continue
                command_path.replace(processed_dir / command_path.name)
            except Exception as error:
                reporter.event(
                    "ATENÇÃO: comando de pod inválido "
                    f"{command_path.name}: {type(error).__name__}: {error}",
                    level="WARNING",
                    color="yellow",
                )
                command_path.replace(
                    processed_dir
                    / f"{command_path.stem}.error{command_path.suffix}"
                )
        monitor_stop.wait(0.5)


def _monitor_pod_resources(
    stop: threading.Event,
    endpoint_registry: mineru.ApiEndpointRegistry,
) -> None:
    warned = False
    while not stop.is_set():
        try:
            for pod_id, usage in pod_resource_usage().items():
                gpu = tuple(usage["gpu"])
                vram = tuple(usage["vram"])
                ram = int(usage["ram"])
                reporter.update_resources(
                    pod_id,
                    gpu=gpu,
                    vram=vram,
                    cpu=int(usage["cpu"]),
                    ram=ram,
                )
                endpoint_registry.update_resources(
                    pod_id,
                    cpu=int(usage["cpu"]),
                    ram=ram,
                    vram=vram,
                )
            warned = False
        except Exception as error:
            if not warned:
                reporter.event(
                    "ATENÇÃO: telemetria RunPod indisponível: "
                    f"{type(error).__name__}: {error}",
                    level="WARNING",
                    color="yellow",
                )
                warned = True
        stop.wait(10)


def run_extract(
    *,
    command_dir: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Audita o inventário, cria pods temporários e extrai a saída remota.

    Pods prontos entram no pool imediatamente. Ao final, os pods RunPod
    conhecidos são apenas parados; nenhum pod é deletado.
    """
    inventory_summary = audit_inventory()
    manifest_path = Path(inventory_summary["extraction_manifest_path"])
    endpoint_registry = mineru.ApiEndpointRegistry(
        settings.mineru_concurrency_per_pod
    )

    def on_ready(
        pod: object,
        health: dict[str, Any],
    ) -> None:
        endpoint_registry.add(
            str(getattr(pod, "api_url")),
            pod_id=str(getattr(pod, "pod_id", "")),
            name=str(getattr(pod, "name", "")),
            gpu_id=getattr(pod, "gpu_id", None),
            health=health,
        )

    extraction_summary: dict[str, Any] | None = None
    monitor_stop = threading.Event()
    graceful_stop = threading.Event()
    monitor_thread: threading.Thread | None = None
    resource_thread: threading.Thread | None = None

    if mineru.pending_count(manifest_path) == 0:
        extraction_summary = mineru.extract(
            endpoint_registry=endpoint_registry,
            manifest_path=manifest_path,
            stop_event=graceful_stop,
            run_id=run_id,
        )
        return {
            "extraction": extraction_summary,
            "reconciliation": extraction_summary["reconciliation"],
        }

    if settings.runpod_serverless_endpoint_id:
        object_storage = (
            ObjectStorage(settings.object_storage_credentials_path)
            if settings.object_storage_credentials_path is not None
            else None
        )
        endpoint_registry.add_serverless(
            settings.runpod_serverless_endpoint_id,
            capacity=settings.runpod_serverless_client_concurrency,
            client=MineruClient(
                endpoint_id=settings.runpod_serverless_endpoint_id,
            ),
        )
        extraction_summary = mineru.extract(
            endpoint_registry=endpoint_registry,
            manifest_path=manifest_path,
            stop_event=graceful_stop,
            run_id=run_id,
            max_source_bytes=(
                settings.runpod_serverless_inline_input_mb
                * 1024
                * 1024
            )
            if object_storage is None
            else None,
            object_storage=object_storage,
        )
        return {
            "extraction": extraction_summary,
            "reconciliation": extraction_summary["reconciliation"],
        }

    try:
        with managed_mineru_pods(on_ready) as coordinator:
            endpoint_registry.set_defective_callback(
                coordinator.quarantine_defective
            )
            for api_url in settings.mineru_api_urls:
                coordinator.add_pod_spec(api_url)

            if command_dir is not None:
                command_dir.mkdir(parents=True, exist_ok=True)
                monitor_thread = threading.Thread(
                    target=_monitor_pod_commands,
                    args=(
                        coordinator,
                        endpoint_registry,
                        command_dir,
                        monitor_stop,
                        graceful_stop,
                    ),
                    name="extract-pod-commands",
                    daemon=True,
                )
                monitor_thread.start()

            resource_thread = threading.Thread(
                target=_monitor_pod_resources,
                args=(monitor_stop, endpoint_registry),
                name="runpod-resource-monitor",
                daemon=True,
            )
            resource_thread.start()

            extraction_summary = mineru.extract(
                endpoint_registry=endpoint_registry,
                manifest_path=manifest_path,
                stop_event=graceful_stop,
                run_id=run_id,
            )
    finally:
        monitor_stop.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=3)
        if resource_thread is not None:
            resource_thread.join(timeout=3)

    return {
        "extraction": extraction_summary,
        "reconciliation": extraction_summary["reconciliation"],
    }


def extract(
    action: str = "start",
    pods: Iterable[str] = (),
    workers: int = 0,
) -> dict[str, Any] | None:
    """Controla a extração e aceita comandos de outros terminais."""
    from .extract_control import dispatch

    normalized_pods = (pods,) if isinstance(pods, str) else tuple(pods)
    return dispatch(action, normalized_pods, workers)


def ingest(
    pod_id: str,
    workers: int,
) -> dict[str, Any] | None:
    """Inicia a extração ou adiciona um pod com capacidade explícita."""
    from .extract_control import start

    if workers < 1:
        raise ValueError("--workers deve ser maior que zero.")
    return start((pod_id,), workers)
