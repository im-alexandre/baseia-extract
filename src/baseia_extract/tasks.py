from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from . import mineru
from .audit import audit_inventory
from .reporting import reporter
from .settings import settings


def _validated_sample_manifest(
    inventory_manifest_path: Path,
    sample_path: Path,
) -> Path:
    if not sample_path.is_file():
        raise FileNotFoundError(
            "Amostra não encontrada. Execute `poe sample` antes de "
            "usar `poe extract --sample`."
        )
    current = pd.read_csv(inventory_manifest_path)
    selected = pd.read_csv(sample_path)
    identity_columns = {"document_id", "revision_id", "sha256"}
    missing_sample_columns = identity_columns.difference(selected.columns)
    if missing_sample_columns:
        raise ValueError(
            "Amostra inválida; colunas ausentes: "
            f"{sorted(missing_sample_columns)}"
        )
    missing_inventory_columns = identity_columns.difference(current.columns)
    if missing_inventory_columns:
        raise ValueError(
            "Inventário auditado inválido; colunas de identidade ausentes: "
            f"{sorted(missing_inventory_columns)}"
        )
    if selected.empty:
        raise RuntimeError("A amostra está vazia.")
    if selected["document_id"].astype(str).duplicated().any():
        raise ValueError("A amostra contém document_id duplicado.")

    current_identity = {
        (
            str(row.document_id),
            str(row.revision_id),
            str(row.sha256),
        )
        for row in current.itertuples(index=False)
    }
    selected_identity = {
        (
            str(row.document_id),
            str(row.revision_id),
            str(row.sha256),
        )
        for row in selected.itertuples(index=False)
    }
    if selected_identity.difference(current_identity):
        raise RuntimeError(
            "A amostra não corresponde ao inventário atual. "
            "Execute `poe sample` novamente."
        )
    return sample_path


def _monitor_commands(
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

                api_urls = payload.get("api_urls", [])
                if not isinstance(api_urls, list):
                    raise TypeError("Campo api_urls deve ser uma lista.")
                workers_value = payload.get("workers")
                workers = (
                    int(workers_value)
                    if workers_value is not None
                    else None
                )
                if workers is not None and workers < 1:
                    raise ValueError("workers deve ser maior que zero.")

                if action == "scale":
                    if workers is None:
                        raise ValueError(
                            "O comando scale exige workers."
                        )
                    updated = sum(
                        endpoint_registry.set_initial_capacity(
                            api_url,
                            workers,
                        )
                        for api_url in api_urls
                    )
                    if updated != len(api_urls):
                        raise LookupError(
                            "Um ou mais endpoints não pertencem à "
                            "extração ativa."
                        )
                    reporter.event(
                        "Capacidade atualizada em runtime | "
                        f"endpoints={updated} | workers={workers}",
                        color="cyan",
                    )
                else:
                    for api_url in api_urls:
                        added = endpoint_registry.add(
                            api_url,
                            name=api_url,
                            client_capacity=workers,
                        )
                        if (
                            not added
                            and workers is not None
                            and not endpoint_registry.set_initial_capacity(
                                api_url,
                                workers,
                            )
                        ):
                            raise LookupError(
                                f"Endpoint não encontrado: {api_url}"
                            )
                    reporter.event(
                        "Endpoint(s) adicionados à extração | "
                        f"quantidade={len(api_urls)}",
                        color="cyan",
                    )

                command_path.replace(processed_dir / command_path.name)
            except Exception as error:
                reporter.event(
                    "ATENÇÃO: comando de extração inválido "
                    f"{command_path.name}: {type(error).__name__}: {error}",
                    level="WARNING",
                    color="yellow",
                )
                command_path.replace(
                    processed_dir
                    / f"{command_path.stem}.error{command_path.suffix}"
                )
        monitor_stop.wait(0.5)


def run_extract(
    *,
    api_urls: tuple[str, ...],
    workers: int = 3,
    sample: bool = False,
    command_dir: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Audita o inventário e extrai usando serviços MinerU HTTP existentes."""
    inventory_summary = audit_inventory()
    manifest_path = Path(inventory_summary["extraction_manifest_path"])
    if sample:
        manifest_path = _validated_sample_manifest(
            manifest_path,
            settings.sample_path,
        )

    endpoint_registry = mineru.ApiEndpointRegistry(
        settings.mineru_concurrency_per_endpoint
    )

    if mineru.pending_count(manifest_path) > 0:
        for api_url in api_urls:
            endpoint_registry.add(
                api_url,
                name=api_url,
                client_capacity=workers or None,
            )
    else:
        reporter.event(
            "Nenhum documento pendente; endpoints não serão consultados.",
            color="green",
        )

    monitor_stop = threading.Event()
    graceful_stop = threading.Event()
    monitor_thread: threading.Thread | None = None

    try:
        if command_dir is not None:
            command_dir.mkdir(parents=True, exist_ok=True)
            monitor_thread = threading.Thread(
                target=_monitor_commands,
                args=(
                    endpoint_registry,
                    command_dir,
                    monitor_stop,
                    graceful_stop,
                ),
                name="extract-commands",
                daemon=True,
            )
            monitor_thread.start()

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

    return {
        "extraction": extraction_summary,
        "reconciliation": extraction_summary["reconciliation"],
    }


def extract(
    action: str = "start",
    api_urls: Iterable[str] = (),
    workers: int = 3,
    sample: bool = False,
) -> dict[str, Any] | None:
    """Controla a extração por URLs mineru-api ou mineru-router."""
    from .extract_control import dispatch

    normalized_urls = (
        (api_urls,)
        if isinstance(api_urls, str)
        else tuple(api_urls)
    )
    return dispatch(action, normalized_urls, workers, sample)
