from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import tempfile
import threading
import time
import uuid
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import anyio
import httpx
import pandas as pd
from mineru_client import MineruClient
from tenacity import (
    Retrying,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from .object_storage import ObjectStorage
from .reporting import reporter
from .schemas import DocumentRecord, ExtractionManifest, ExtractionResult
from .settings import settings


@dataclass(slots=True)
class ApiEndpoint:
    api_url: str
    pod_id: str | None
    name: str
    gpu_id: str | None
    service_capacity: int
    client_capacity: int
    client_capacity_limit: int
    initial_capacity: int
    api_queued: int = 0
    in_flight: int = 0
    healthy: bool = True
    serverless_client: MineruClient | None = None
    draining: bool = False
    capacity_before_drain: int = 0
    low_pressure_samples: int = 0
    resume_samples: int = 0
    gpu_count: int = 1
    cpu_usage: int = 0
    cpu_high_pressure_samples: int = 0
    cpu_increase_blocked: bool = False
    transport_failures: int = 0
    connect_failures: deque[float] = field(default_factory=deque)
    circuit_open_until: float = 0.0
    circuit_successes: int = 0
    completions: deque[tuple[float, int, float]] = field(default_factory=deque)
    epoch_started_at: float | None = None
    settling_until: float = 0.0
    epoch_capacity: int = 0
    epoch_evaluated: bool = False
    epoch_pages_per_minute: float = 0.0
    epoch_window_rates: list[float] = field(default_factory=list)
    throughput_baseline: float = 0.0
    efficient_capacity: int = 0
    controller_samples: int = 0

    @property
    def key(self) -> str:
        return self.pod_id or self.api_url

    @property
    def free(self) -> int:
        return max(0, self.client_capacity - self.in_flight)

    @property
    def circuit_open(self) -> bool:
        return self.circuit_open_until > 0


class ResultDownloadError(RuntimeError):
    """Falha final de transporte; a tarefa MinerU não deve ser reenviada."""


class TaskRecoveryError(ResultDownloadError):
    """A tarefa já foi aceita pelo servidor e deve ser retomada depois."""


class TaskIdentityError(ResultDownloadError):
    """O servidor não confirmou a chave; um novo POST não é seguro."""

    def __init__(
        self,
        message: str,
        *,
        returned_task_id: str | None,
    ) -> None:
        super().__init__(message)
        self.returned_task_id = returned_task_id


class TaskRequestError(RuntimeError):
    """A API rejeitou permanentemente a requisição do documento."""


class TaskTerminalError(RuntimeError):
    """A API confirmou que a tarefa terminou em falha; pode gerar nova task."""


class ExtractionStopped(RuntimeError):
    """A extração parou antes que a tarefa adquirisse um endpoint."""


# Um restart do router apaga a tabela de tarefas em memória, mas não o pacote
# persistido. Só liberamos um novo POST após leituras consecutivas do 404 com
# o endpoint original saudável; falhas de transporte nunca contam como 404.
_ORPHAN_TASK_404_CONFIRMATIONS = 3
_ORPHAN_TASK_404_GRACE_SECONDS = 2.0


class ApiEndpointRegistry:
    """Registro transitório da capacidade anunciada pelos serviços MinerU."""

    def __init__(self, concurrency_limit: int) -> None:
        self._concurrency_limit = concurrency_limit
        self._condition = threading.Condition()
        self._first_ready = threading.Event()
        self._endpoints: dict[str, ApiEndpoint] = {}
        self._defective: set[str] = set()
        self._on_defective: Callable[[str, str], None] | None = None

    def set_defective_callback(
        self,
        callback: Callable[[str, str], None],
    ) -> None:
        self._on_defective = callback

    def add(
        self,
        api_url: str,
        *,
        pod_id: str = "",
        name: str = "",
        gpu_id: str | None = None,
        health: dict[str, Any] | None = None,
    ) -> bool:
        url = api_url.strip().rstrip("/")
        health = health or _health(url)
        advertised = max(
            1,
            _as_int(
                health.get("max_concurrent_requests"),
                self._concurrency_limit,
            ),
        )
        requested = _as_int(
            health.get("_client_capacity_override"),
            self._concurrency_limit,
        )
        client_capacity = min(advertised, max(1, requested))
        endpoint = ApiEndpoint(
            api_url=url,
            pod_id=pod_id or None,
            name=name or pod_id or url,
            gpu_id=gpu_id,
            service_capacity=advertised,
            client_capacity=client_capacity,
            client_capacity_limit=advertised,
            initial_capacity=client_capacity,
            api_queued=_as_int(health.get("queued_tasks"), 0),
        )
        with self._condition:
            if url in self._endpoints:
                return False
            self._endpoints[url] = endpoint
            self._first_ready.set()
            self._condition.notify_all()
        reporter.register_pod(
            endpoint.key,
            label=endpoint.name,
            gpu=endpoint.gpu_id,
            service_capacity=endpoint.service_capacity,
            client_capacity=endpoint.client_capacity,
            api_queued=endpoint.api_queued,
        )
        return True

    def wait_for_first(self, timeout: float) -> bool:
        return self._first_ready.wait(timeout)

    def add_serverless(
        self,
        endpoint_id: str,
        *,
        capacity: int,
        client: MineruClient,
    ) -> bool:
        endpoint = ApiEndpoint(
            api_url=f"runpod://{endpoint_id}",
            pod_id=None,
            name=f"serverless:{endpoint_id}",
            gpu_id=None,
            service_capacity=capacity,
            client_capacity=capacity,
            client_capacity_limit=capacity,
            initial_capacity=capacity,
            serverless_client=client,
        )
        with self._condition:
            if endpoint.api_url in self._endpoints:
                return False
            self._endpoints[endpoint.api_url] = endpoint
            self._first_ready.set()
            self._condition.notify_all()
        reporter.register_pod(
            endpoint.key,
            label=endpoint.name,
            gpu="pool dinâmico",
            service_capacity=capacity,
            client_capacity=capacity,
            api_queued=0,
        )
        return True

    def acquire(
        self,
        stop_event: threading.Event | None = None,
    ) -> ApiEndpoint:
        with self._condition:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise ExtractionStopped
                available = [
                    endpoint
                    for endpoint in self._endpoints.values()
                    if endpoint.healthy
                    and not endpoint.circuit_open
                    and endpoint.free > 0
                ]
                if available:
                    endpoint = min(
                        available,
                        key=lambda item: (
                            item.in_flight / item.client_capacity,
                            item.in_flight,
                            item.name,
                        ),
                    )
                    endpoint.in_flight += 1
                    return endpoint
                self._condition.wait(0.5)

    def acquire_preferred(
        self,
        api_url: str,
        *,
        fallback_if_missing: bool = False,
        stop_event: threading.Event | None = None,
    ) -> ApiEndpoint:
        """
        Reserva o endpoint original ou outro saudável se ele saiu do pool.

        Um endpoint presente, mas temporariamente indisponível, continua sendo
        aguardado para evitar duplicar uma tarefa ainda recuperável no disco
        daquele pod. O fallback só ocorre quando a URL antiga não pertence ao
        pool atual.
        """
        normalized = api_url.rstrip("/")
        with self._condition:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise ExtractionStopped
                endpoint = self._endpoints.get(normalized)
                if endpoint is not None and endpoint.healthy and endpoint.free > 0:
                    endpoint.in_flight += 1
                    return endpoint
                if endpoint is None and fallback_if_missing:
                    available = [
                        candidate
                        for candidate in self._endpoints.values()
                        if candidate.healthy
                        and not candidate.circuit_open
                        and candidate.free > 0
                    ]
                    if available:
                        fallback = min(
                            available,
                            key=lambda item: (
                                item.in_flight / item.client_capacity,
                                item.in_flight,
                                item.name,
                            ),
                        )
                        fallback.in_flight += 1
                        return fallback
                self._condition.wait(0.5)

    def acquire_for_reconciliation(
        self,
        stop_event: threading.Event | None = None,
    ) -> ApiEndpoint:
        """Usa qualquer pod saudável para consultar o volume compartilhado."""
        with self._condition:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise ExtractionStopped
                available = [
                    endpoint
                    for endpoint in self._endpoints.values()
                    if endpoint.healthy and endpoint.free > 0
                ]
                if available:
                    endpoint = min(
                        available,
                        key=lambda item: (item.in_flight, item.name),
                    )
                    endpoint.in_flight += 1
                    return endpoint
                self._condition.wait(0.5)

    def release(self, endpoint: ApiEndpoint) -> None:
        with self._condition:
            current = self._endpoints.get(endpoint.api_url)
            if current is not None:
                current.in_flight = max(0, current.in_flight - 1)
            self._condition.notify_all()

    def _record_connect_failure(self, endpoint: ApiEndpoint) -> None:
        now = time.monotonic()
        opened = False
        with self._condition:
            endpoint.connect_failures.append(now)
            while (
                endpoint.connect_failures
                and now - endpoint.connect_failures[0]
                > settings.mineru_circuit_window_seconds
            ):
                endpoint.connect_failures.popleft()
            endpoint.circuit_successes = 0
            if (
                len(endpoint.connect_failures)
                >= settings.mineru_circuit_failure_threshold
                and not endpoint.circuit_open
            ):
                endpoint.circuit_open_until = (
                    now + settings.mineru_circuit_cooldown_seconds
                )
                opened = True
            self._condition.notify_all()
        if opened:
            reporter.update_circuit(endpoint.key, "aberto")
            reporter.event(
                f"Circuito de admissão aberto | pod={endpoint.name} | "
                f"falhas={len(endpoint.connect_failures)}",
                level="WARNING",
                color="yellow",
            )

    def _record_health_success(self, endpoint: ApiEndpoint) -> None:
        now = time.monotonic()
        closed = False
        with self._condition:
            endpoint.connect_failures.clear()
            if endpoint.circuit_open_until:
                endpoint.circuit_successes += 1
                if (
                    now >= endpoint.circuit_open_until
                    and endpoint.circuit_successes
                    >= settings.mineru_circuit_recovery_successes
                ):
                    endpoint.circuit_open_until = 0.0
                    endpoint.circuit_successes = 0
                    closed = True
            self._condition.notify_all()
        if closed:
            reporter.update_circuit(endpoint.key, "fechado")
            reporter.event(
                f"Circuito de admissão recuperado | pod={endpoint.name}",
                color="green",
            )

    def mark_defective(self, endpoint: ApiEndpoint, reason: str) -> None:
        callback: Callable[[str, str], None] | None = None
        with self._condition:
            endpoint.healthy = False
            endpoint.client_capacity = 0
            if endpoint.key not in self._defective:
                self._defective.add(endpoint.key)
                callback = self._on_defective
            self._condition.notify_all()
        reporter.update_health(endpoint.key, healthy=False)
        if callback is not None and endpoint.pod_id:
            callback(endpoint.pod_id, reason)

    def reduce_capacity(
        self,
        endpoint: ApiEndpoint,
        reason: str,
    ) -> None:
        with self._condition:
            current = self._endpoints.get(endpoint.api_url)
            if current is None or current.draining:
                return
            previous = current.client_capacity
            current.client_capacity = max(
                1,
                math.floor(previous * 0.75),
            )
            current.low_pressure_samples = 0
            changed = current.client_capacity != previous
            self._condition.notify_all()
        if changed:
            reporter.update_capacity(
                endpoint.key,
                current.client_capacity,
            )
            reporter.event(
                f"Capacidade reduzida | pod={endpoint.name} | "
                f"{previous}->{current.client_capacity} | motivo={reason}",
                level="WARNING",
                color="yellow",
            )

    def set_initial_capacity(
        self,
        pod_key: str,
        capacity: int,
    ) -> bool:
        with self._condition:
            endpoint = next(
                (
                    item
                    for item in self._endpoints.values()
                    if item.key == pod_key
                ),
                None,
            )
            if endpoint is None:
                return False
            previous = endpoint.client_capacity
            endpoint.initial_capacity = min(
                endpoint.client_capacity_limit,
                max(1, capacity),
            )
            endpoint.client_capacity = endpoint.initial_capacity
            endpoint.draining = False
            endpoint.low_pressure_samples = 0
            endpoint.resume_samples = 0
            self._condition.notify_all()
        reporter.update_capacity(endpoint.key, endpoint.client_capacity)
        reporter.event(
            f"Capacidade inicial atualizada | pod={endpoint.name} | "
            f"{previous}->{endpoint.client_capacity}",
            color="cyan",
        )
        return True

    def set_all_capacities(self, capacity: int) -> int:
        if capacity < 1:
            raise ValueError("A capacidade deve ser maior que zero.")
        with self._condition:
            pod_keys = tuple(
                endpoint.key
                for endpoint in self._endpoints.values()
                if endpoint.serverless_client is None
            )
        return sum(
            self.set_initial_capacity(pod_key, capacity)
            for pod_key in pod_keys
        )

    def update_resources(
        self,
        pod_key: str,
        *,
        cpu: int,
        ram: int,
        vram: tuple[int, ...],
    ) -> None:
        changed = False
        resumed = False
        previous = 0
        pressure = max((ram, *vram), default=ram)
        with self._condition:
            endpoint = next(
                (
                    item
                    for item in self._endpoints.values()
                    if item.key == pod_key
                ),
                None,
            )

            if endpoint is None or endpoint.serverless_client is not None:
                return
            endpoint.gpu_count = max(1, len(vram))
            endpoint.cpu_usage = max(0, cpu)
            if endpoint.cpu_usage >= settings.mineru_autotune_cpu_high_percent:
                endpoint.cpu_high_pressure_samples += 1
                if (
                    endpoint.cpu_high_pressure_samples
                    >= settings.mineru_autotune_cpu_high_samples
                ):
                    endpoint.cpu_increase_blocked = True
            elif endpoint.cpu_usage < settings.mineru_autotune_cpu_recovery_percent:
                endpoint.cpu_high_pressure_samples = 0
                endpoint.cpu_increase_blocked = False
            else:
                endpoint.cpu_high_pressure_samples = 0
            previous = endpoint.client_capacity

            if pressure >= 75:
                if not endpoint.draining:
                    endpoint.capacity_before_drain = max(
                        1,
                        endpoint.client_capacity,
                    )
                endpoint.draining = True
                endpoint.client_capacity = 0
                endpoint.low_pressure_samples = 0
                endpoint.resume_samples = 0
            elif endpoint.draining:
                if pressure < 65:
                    endpoint.resume_samples += 1
                    if endpoint.resume_samples >= 3:
                        endpoint.draining = False
                        endpoint.client_capacity = min(
                            endpoint.client_capacity_limit,
                            max(
                                1,
                                endpoint.efficient_capacity
                                or endpoint.capacity_before_drain,
                            ),
                        )
                        endpoint.resume_samples = 0
                        resumed = True
                else:
                    endpoint.resume_samples = 0
            elif pressure > 70:
                endpoint.client_capacity = max(
                    1,
                    math.floor(endpoint.client_capacity * 0.75),
                )
                endpoint.low_pressure_samples = 0
            else:
                # Recursos saudáveis apenas permitem o controlador de throughput agir.
                endpoint.low_pressure_samples = 0

            changed = endpoint.client_capacity != previous
            self._condition.notify_all()

        if changed:
            reporter.update_capacity(
                endpoint.key,
                endpoint.client_capacity,
                draining=endpoint.draining,
            )
            action = (
                "retomada"
                if resumed
                else "drenagem"
                if endpoint.draining
                else "ajuste"
            )
            reporter.event(
                f"Capacidade dinâmica | pod={endpoint.name} | "
                f"{previous}->{endpoint.client_capacity} | "
                f"pressão={pressure}% | ação={action}",
                color="green" if resumed else "yellow",
            )

    @staticmethod
    def _reset_epoch(endpoint: ApiEndpoint, now: float) -> None:
        endpoint.completions.clear()
        endpoint.settling_until = now + settings.mineru_autotune_settling_seconds
        endpoint.epoch_started_at = endpoint.settling_until
        endpoint.epoch_capacity = endpoint.client_capacity
        endpoint.epoch_evaluated = False
        endpoint.epoch_window_rates.clear()

    def record_completion(
        self,
        endpoint: ApiEndpoint,
        *,
        pages: int,
        duration: float,
        now: float | None = None,
    ) -> dict[str, float | int | str]:
        """Compara somente epochs completos de um mesmo nível de workers."""
        now = time.monotonic() if now is None else now
        with self._condition:
            current = self._endpoints.get(endpoint.api_url)
            if current is None:
                return {}
            if current.epoch_capacity != current.client_capacity:
                self._reset_epoch(current, now)
            if now < current.settling_until:
                return {
                    "pages_per_minute": 0.0,
                    "documents_per_minute": 0.0,
                    "p50_seconds": 0.0,
                    "p95_seconds": 0.0,
                    "efficient_capacity": current.efficient_capacity,
                    "client_capacity": current.client_capacity,
                    "epoch_capacity": current.epoch_capacity,
                    "epoch_completions": 0,
                    "epoch_elapsed_seconds": 0.0,
                    "controller_action": "settling",
                }
            current.completions.append((now, max(1, pages), max(duration, 0.001)))
            samples = tuple(current.completions)
            epoch_started_at = current.epoch_started_at
            elapsed = (
                max(1.0, now - epoch_started_at)
                if epoch_started_at is not None
                else 1.0
            )
            pages_per_minute = sum(row[1] for row in samples) * 60 / elapsed
            docs_per_minute = len(samples) * 60 / elapsed
            latencies = [row[2] for row in samples]
            p50 = statistics.median(latencies)
            p95 = sorted(latencies)[max(0, math.ceil(len(latencies) * .95) - 1)]
            previous = current.client_capacity
            action = "collecting"
            cpu_increase_deferred = False
            complete_window = (
                len(samples)
                >= max(
                    settings.mineru_autotune_min_samples,
                    current.epoch_capacity,
                )
                and elapsed >= settings.mineru_autotune_window_seconds
            )
            if complete_window and not current.epoch_evaluated:
                current.epoch_window_rates.append(pages_per_minute)
                current.completions.clear()
                current.epoch_started_at = now
                action = "window_collected"
            if (
                len(current.epoch_window_rates) >= 2
                and not current.epoch_evaluated
                and not current.draining
            ):
                current.epoch_evaluated = True
                sustained_rate = min(current.epoch_window_rates[-2:])
                current.epoch_pages_per_minute = sustained_rate
                if current.throughput_baseline == 0:
                    current.throughput_baseline = sustained_rate
                    current.efficient_capacity = current.client_capacity
                    action = "baseline"
                    if current.cpu_increase_blocked:
                        action = "baseline_cpu_guard"
                        cpu_increase_deferred = True
                    else:
                        current.client_capacity = min(
                            current.client_capacity_limit,
                            current.client_capacity + max(1, current.gpu_count),
                        )
                elif sustained_rate >= current.throughput_baseline * 1.05:
                    current.throughput_baseline = sustained_rate
                    current.efficient_capacity = current.client_capacity
                    action = "advance"
                    if current.cpu_increase_blocked:
                        action = "advance_cpu_guard"
                        cpu_increase_deferred = True
                    else:
                        current.client_capacity = min(
                            current.client_capacity_limit,
                            current.client_capacity + max(1, current.gpu_count),
                        )
                elif current.client_capacity > current.efficient_capacity:
                    current.client_capacity = current.efficient_capacity
                    action = "revert"
                else:
                    action = "plateau"
            metrics: dict[str, float | int | str] = {
                "pages_per_minute": round(pages_per_minute, 2),
                "documents_per_minute": round(docs_per_minute, 2),
                "p50_seconds": round(p50, 3),
                "p95_seconds": round(p95, 3),
                "efficient_capacity": current.efficient_capacity,
                "client_capacity": current.client_capacity,
                "epoch_capacity": current.epoch_capacity,
                "epoch_completions": len(samples),
                "epoch_elapsed_seconds": round(elapsed, 3),
                "controller_action": action,
            }
            changed = current.client_capacity != previous
            if changed or cpu_increase_deferred:
                self._reset_epoch(current, now)
            self._condition.notify_all()
        reporter.update_throughput(
            endpoint.key,
            pages_per_minute=float(metrics["pages_per_minute"]),
            documents_per_minute=float(metrics["documents_per_minute"]),
            p50_seconds=float(metrics["p50_seconds"]),
            p95_seconds=float(metrics["p95_seconds"]),
        )
        if changed:
            reporter.event(
                "Controle por throughput | "
                f"pod={endpoint.name} | pages/min={metrics['pages_per_minute']} | "
                f"workers={previous}->{current.client_capacity} | ação={action}",
                color="green" if current.client_capacity > previous else "yellow",
            )
            reporter.update_capacity(endpoint.key, current.client_capacity)
        elif cpu_increase_deferred:
            reporter.event(
                "Aumento de capacidade adiado por CPU | "
                f"pod={endpoint.name} | cpu={current.cpu_usage}% | "
                f"amostras={current.cpu_high_pressure_samples} | "
                f"workers={current.client_capacity}",
                color="yellow",
            )
        return metrics

    @property
    def endpoint_count(self) -> int:
        with self._condition:
            return len(self._endpoints)

    @property
    def total_capacity(self) -> int:
        with self._condition:
            return sum(
                endpoint.client_capacity
                for endpoint in self._endpoints.values()
                if endpoint.healthy
            )

    def refresh_health(self) -> None:
        with self._condition:
            endpoints = tuple(self._endpoints.values())
        for endpoint in endpoints:
            if endpoint.serverless_client is not None:
                continue
            try:
                health = _health(endpoint.api_url, timeout=3.0)
                advertised = max(
                    1,
                    _as_int(
                        health.get("max_concurrent_requests"),
                        endpoint.service_capacity,
                    ),
                )
                with self._condition:
                    endpoint.healthy = True
                    endpoint.transport_failures = 0
                    endpoint.service_capacity = advertised
                    endpoint.client_capacity_limit = advertised
                    endpoint.client_capacity = min(
                        endpoint.client_capacity,
                        advertised,
                    )
                    endpoint.api_queued = _as_int(
                        health.get("queued_tasks"),
                        0,
                    )
                    self._condition.notify_all()
                reporter.update_health(
                    endpoint.key,
                    healthy=True,
                    api_queued=endpoint.api_queued,
                    service_capacity=advertised,
                )
                reporter.update_capacity(
                    endpoint.key,
                    endpoint.client_capacity,
                    draining=endpoint.draining,
                )
                self._record_health_success(endpoint)
            except httpx.ConnectError:
                # Uma falha isolada não muda capacidade nem descarta jobs.
                with self._condition:
                    endpoint.transport_failures += 1
                self._record_connect_failure(endpoint)
                reporter.event(
                    f"Conexão transitória indisponível | pod={endpoint.name}",
                    level="WARNING",
                    color="yellow",
                )
            except Exception:
                with self._condition:
                    endpoint.healthy = False
                reporter.update_health(endpoint.key, healthy=False)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._condition:
            return [
                {
                    "pod_id": endpoint.pod_id,
                    "name": endpoint.name,
                    "gpu_id": endpoint.gpu_id,
                    "api_url": endpoint.api_url,
                    "healthy": endpoint.healthy,
                    "service_capacity": endpoint.service_capacity,
                    "client_capacity": endpoint.client_capacity,
                    "client_capacity_limit": (
                        endpoint.client_capacity_limit
                    ),
                    "initial_capacity": endpoint.initial_capacity,
                    "in_flight": endpoint.in_flight,
                    "draining": endpoint.draining,
                    "circuit": (
                        "open"
                        if endpoint.circuit_open
                        else "closed"
                    ),
                    "pages_per_minute": endpoint.throughput_baseline,
                    "efficient_capacity": endpoint.efficient_capacity,
                    "transport": (
                        "runpod-serverless"
                        if endpoint.serverless_client is not None
                        else "mineru-api"
                    ),
                }
                for endpoint in self._endpoints.values()
            ]


@dataclass(slots=True)
class ExtractionConfig:
    endpoint_registry: ApiEndpointRegistry
    manifest_path: Path
    output_root: Path
    retries: int
    overwrite: bool
    run_id: str
    manifests: ManifestStore
    max_source_bytes: int | None = None
    object_storage: ObjectStorage | None = None


@dataclass(slots=True)
class WorkItem:
    position: int
    document: DocumentRecord
    output_dir: Path
    row: dict[str, Any] = field(default_factory=dict)


class ManifestStore:
    """Manifestos individuais, atômicos e recuperáveis entre execuções."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, sha256: str) -> Path:
        return self.root / sha256[:2] / f"{sha256}.json"

    def load(self, item: WorkItem) -> ExtractionManifest:
        path = self.path_for(item.document.sha256)
        try:
            return ExtractionManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, ValueError):
            return ExtractionManifest(
                sha256=item.document.sha256,
                document_id=item.document.document_id,
                path=item.document.path,
                filename=item.document.filename,
                output_dir=item.output_dir,
                row=item.row,
            )

    def save(self, manifest: ExtractionManifest) -> None:
        path = self.path_for(manifest.sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(
                manifest.model_dump_json(indent=2), encoding="utf-8"
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def update(
        self,
        item: WorkItem,
        **values: Any,
    ) -> ExtractionManifest:
        manifest = self.load(item)
        manifest = manifest.model_copy(
            update={
                **values,
                "updated_at": datetime_now_iso(),
                "row": item.row,
                "path": item.document.path,
                "output_dir": item.output_dir,
            }
        )
        self.save(manifest)
        return manifest


def datetime_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _as_int(value: object, default: int) -> int:
    try:
        if value is None or math.isnan(float(value)):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _hardware_failure(message: str) -> bool:
    normalized = message.casefold()
    return any(
        marker in normalized
        for marker in (
            "cuda-capable device(s) is/are busy or unavailable",
            "cudaerrornoDevice".casefold(),
            "no cuda-capable device is detected",
            "nvidia driver is not loaded",
        )
    )


def _memory_pressure_failure(message: str) -> bool:
    normalized = message.casefold()
    return any(
        marker in normalized
        for marker in (
            "out of memory",
            "cuda oom",
            "cudaerroroutofmemory",
            "cannot allocate memory",
            "killed process",
        )
    )


def _health(
    api_url: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    response = httpx.get(
        f"{api_url}/health",
        timeout=timeout or settings.mineru_health_timeout_seconds,
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("Resposta /health inválida.")
    return payload


def _submit(
    pdf_path: Path,
    api_url: str,
    *,
    correlation_key: str,
    task_id: str,
) -> dict[str, Any]:
    if task_id != correlation_key:
        raise ValueError(
            "A task_id idempotente deve ser o SHA-256 do documento."
        )
    fields = {
        # MinerU groups English and Latin-script languages (including
        # Brazilian Portuguese) under the OCR profile named "ch".
        "lang_list": "ch",
        "backend": settings.mineru_backend,
        "parse_method": "auto",
        "formula_enable": "true",
        "table_enable": "true",
        "return_md": "true",
        "return_middle_json": "true",
        "return_model_output": "false",
        "return_content_list": "true",
        "return_images": "true",
        "response_format_zip": "true",
    }
    try:
        with pdf_path.open("rb") as pdf:
            response = httpx.post(
                f"{api_url}/tasks",
                data=fields,
                files={"files": (f"{correlation_key}.pdf", pdf, "application/pdf")},
                headers={"Idempotency-Key": correlation_key},
                timeout=settings.mineru_submit_timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
    except (httpx.TimeoutException, httpx.NetworkError) as error:
        raise TaskRecoveryError(
            f"POST ambíguo para {correlation_key}; preservando task_id {task_id}: "
            f"{type(error).__name__}: {error}"
        ) from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code >= 500:
            raise TaskRecoveryError(
                f"POST ambíguo para {correlation_key}; preservando task_id {task_id}: "
                f"{type(error).__name__}: {error}"
            ) from error
        raise TaskRequestError(
            f"POST rejeitado para {correlation_key}: HTTP "
            f"{error.response.status_code}: {error.response.text[:500]}"
        ) from error
    if not isinstance(payload, dict):
        raise TypeError("Resposta de submissão inválida.")
    returned_task_id = payload.get("task_id")
    if returned_task_id != task_id:
        raise TaskIdentityError(
            "Resposta de submissão não confirmou a identidade determinística: "
            f"esperado={task_id!r} recebido={returned_task_id!r}.",
            returned_task_id=(
                returned_task_id
                if isinstance(returned_task_id, str) and returned_task_id
                else None
            ),
        )
    return payload


def _reconcile_submission(
    api_url: str,
    correlation_key: str,
) -> dict[str, Any] | None:
    """Obtém a tarefa persistida pelo router antes de permitir novo POST."""
    tasks = _persisted_tasks(api_url, correlation_key)
    completed = [
        item
        for item in tasks
        if str(item.get("status", "")).casefold() == "completed"
        and item.get("persisted_at")
        and item.get("package_dir")
        and isinstance(item.get("artifacts"), list)
        and item["artifacts"]
    ]
    active = [
        item
        for item in tasks
        if str(item.get("status", "")).casefold()
        not in {"completed", "failed", "error", "cancelled"}
    ]
    terminal = [item for item in tasks if item not in completed + active]
    task = next(iter(completed or active or terminal), None)
    task_id = task.get("task_id") if isinstance(task, dict) else None
    if not isinstance(task_id, str) or not task_id:
        if not tasks:
            return None
        raise TaskRecoveryError(
            f"Router não retornou task_id persistido para {correlation_key}."
        )
    return task


def _persisted_tasks(
    api_url: str,
    correlation_key: str,
) -> list[dict[str, Any]]:
    """Lê o índice persistente sem inferir que uma ausência é falha remota."""
    try:
        response = httpx.get(
            f"{api_url}/persisted-tasks/{correlation_key}",
            timeout=settings.mineru_health_timeout_seconds,
            headers={"Accept": "application/json"},
        )
    except (httpx.TimeoutException, httpx.NetworkError) as error:
        raise TaskRecoveryError(
            f"Reconciliação indisponível para {correlation_key}: {type(error).__name__}: {error}"
        ) from error
    if response.status_code == 404:
        return []
    try:
        response.raise_for_status()
        payload = response.json()
        return [
            item
            for item in payload.get("tasks", [])
            if isinstance(item, dict) and item.get("task_id")
        ] if isinstance(payload, dict) else []
    except (httpx.HTTPStatusError, ValueError, TypeError) as error:
        raise TaskRecoveryError(
            f"Reconciliação inválida para {correlation_key}: {type(error).__name__}: {error}"
        ) from error


def _recover_orphaned_task(
    *,
    original_api_url: str,
    persisted_api_urls: tuple[str, ...],
    correlation_key: str,
    task_id: str,
) -> dict[str, Any] | bool | None:
    """Recupera pacote persistido ou confirma que a task sumiu após restart.

    ``None`` significa task órfã confirmada e ``False`` que ela ainda está
    ativa. Erros de HTTP/transporte são
    deliberadamente propagados como ``TaskRecoveryError`` para impedir POST
    duplicado quando o estado remoto não puder ser observado com segurança.
    """

    def probe() -> tuple[str, dict[str, Any] | None]:
        for api_url in persisted_api_urls:
            tasks = _persisted_tasks(api_url, correlation_key)
            for persisted in tasks:
                if (
                    str(persisted.get("status", "")).casefold()
                    == "completed"
                    and persisted.get("persisted_at")
                    and persisted.get("package_dir")
                    and isinstance(persisted.get("artifacts"), list)
                    and persisted["artifacts"]
                ):
                    return "persisted", persisted
            prior = next(
                (
                    persisted
                    for persisted in tasks
                    if persisted.get("task_id") == task_id
                ),
                None,
            )
            if prior is not None and str(
                prior.get("status", "")
            ).casefold() in {"failed", "error", "cancelled"}:
                raise TaskTerminalError(
                    f"Tarefa persistida {task_id} terminou com status "
                    f"{prior.get('status')}: {prior}"
                )

        try:
            response = httpx.get(
                f"{original_api_url}/tasks/{task_id}",
                timeout=settings.mineru_health_timeout_seconds,
                headers={"Accept": "application/json"},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TaskRecoveryError(
                f"Estado da tarefa {task_id} indisponível no endpoint original: "
                f"{type(error).__name__}: {error}"
            ) from error

        if response.status_code != 404:
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError, TypeError) as error:
                raise TaskRecoveryError(
                    f"Estado inválido da tarefa {task_id}: {type(error).__name__}: {error}"
                ) from error
            if not isinstance(payload, dict):
                raise TaskRecoveryError(f"Resposta /tasks/{task_id} inválida.")
            status = str(payload.get("status", "")).casefold()
            if status in {"failed", "error", "cancelled"}:
                raise TaskTerminalError(
                    f"Tarefa {task_id} terminou com status {status}: {payload}"
                )
            return "active", None

        try:
            _health(original_api_url)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise TaskRecoveryError(
                f"Endpoint original não está saudável ao confirmar ausência de {task_id}: "
                f"{type(error).__name__}: {error}"
            ) from error
        return "missing", None

    retrying = Retrying(
        stop=stop_after_attempt(_ORPHAN_TASK_404_CONFIRMATIONS),
        wait=wait_fixed(_ORPHAN_TASK_404_GRACE_SECONDS),
        retry=retry_if_result(lambda result: result[0] == "missing"),
        # Após o último 404 confirmado, devolve o resultado ``missing`` para
        # que o chamador registre a órfã e reenvie. Sem este callback o
        # Tenacity transforma a confirmação em RetryError.
        retry_error_callback=lambda retry_state: retry_state.outcome.result(),
        reraise=True,
    )
    state, persisted = retrying(probe)
    if state == "persisted":
        return persisted
    if state == "active":
        return False
    return None


def _wait_persisted_result(
    api_url: str,
    correlation_key: str,
    task_id: str,
) -> dict[str, Any]:
    """Confirma o pacote atômico no volume; não baixa ZIP no caminho crítico."""
    deadline = time.monotonic() + max(
        settings.mineru_task_timeout_seconds,
        settings.mineru_result_timeout_seconds,
    ) + 300.0
    last_error = "registro persistido ainda indisponível"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(
                f"{api_url}/persisted-tasks/{correlation_key}",
                timeout=settings.mineru_health_timeout_seconds,
                headers={"Accept": "application/json"},
            )
            if response.status_code == 404:
                time.sleep(settings.mineru_poll_interval_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
            matching = next(
                (
                    candidate
                    for candidate in tasks
                    if isinstance(candidate, dict)
                    and candidate.get("task_id") == task_id
                ),
                None,
            )
            if matching is not None and str(
                matching.get("status", "")
            ).casefold() in {"failed", "error", "cancelled"}:
                raise TaskTerminalError(
                    f"Tarefa persistida terminou com status "
                    f"{matching.get('status')}: {matching}"
                )
            task = next(
                (
                    candidate
                    for candidate in tasks
                    if isinstance(candidate, dict)
                    and candidate.get("task_id") == task_id
                    and candidate.get("status") == "completed"
                    and candidate.get("persisted_at")
                    and candidate.get("package_dir")
                    and isinstance(candidate.get("artifacts"), list)
                    and candidate["artifacts"]
                ),
                None,
            )
            if task is not None:
                return task
            last_error = "tarefa ainda não foi persistida atomicamente no volume"
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            last_error = f"{type(error).__name__}: {error}"
        except (httpx.HTTPStatusError, ValueError, TypeError) as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(settings.mineru_poll_interval_seconds)
    raise TaskRecoveryError(
        f"Confirmação do volume expirou para {task_id}; sem reenvio: {last_error}"
    )


def _retryable_result_error(error: BaseException) -> bool:
    if isinstance(error, httpx.TimeoutException | httpx.NetworkError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status in {408, 429} or status >= 500
    return False


def _extract_result_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.",
            dir=output_dir.parent,
        )
    )
    stage_root = stage.resolve()
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                member_path = PurePosixPath(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(
                        f"Entrada insegura no ZIP MinerU: {member.filename}"
                    )
                target = (
                    stage_root / Path(*member_path.parts)
                ).resolve()
                if target != stage_root and stage_root not in target.parents:
                    raise ValueError(
                        f"Entrada fora do destino no ZIP: {member.filename}"
                    )
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source:
                    with target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)

        if not _completed(stage):
            raise ValueError("ZIP MinerU sem middle JSON válido.")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        os.replace(stage, output_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _download_result_zip(
    api_url: str,
    task_id: str,
    output_dir: Path,
    *,
    retries: int,
) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        retrying = Retrying(
            stop=stop_after_attempt(retries + 1),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception(_retryable_result_error),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                handle, temporary_name = tempfile.mkstemp(
                    suffix=".zip",
                    prefix=f".{task_id}.",
                    dir=output_dir.parent,
                )
                os.close(handle)
                zip_path = Path(temporary_name)
                try:
                    timeout = httpx.Timeout(
                        connect=30,
                        read=settings.mineru_result_timeout_seconds,
                        write=300,
                        pool=30,
                    )
                    with httpx.stream(
                        "GET",
                        f"{api_url}/tasks/{task_id}/result",
                        timeout=timeout,
                    ) as response:
                        response.raise_for_status()
                        content_type = response.headers.get(
                            "content-type",
                            "",
                        )
                        if "application/zip" not in content_type.casefold():
                            raise ValueError(
                                "Resultado MinerU não retornou ZIP: "
                                f"{content_type or 'sem content-type'}"
                            )
                        with zip_path.open("wb") as destination:
                            for chunk in response.iter_bytes(
                                chunk_size=1024 * 1024
                            ):
                                destination.write(chunk)
                    _extract_result_zip(zip_path, output_dir)
                finally:
                    zip_path.unlink(missing_ok=True)
    except Exception as error:
        raise ResultDownloadError(
            f"Falha ao baixar ZIP da tarefa {task_id} sem reenviar o PDF: "
            f"{type(error).__name__}: {error}"
        ) from error


def _save_serverless_result(
    result: dict[str, Any],
    output_dir: Path,
    *,
    artifact_uri: str | None = None,
) -> None:
    if artifact_uri:
        MineruClient.save_s3_tarball(result, output_dir)
    else:
        MineruClient.save_tarball(result, output_dir)
    entry = MineruClient.first(result)
    metadata = {
        key: value
        for key, value in entry.items()
        if key not in {"tarball_b64", "tarball_url", "images"}
    }
    if artifact_uri:
        metadata["artifact_uri"] = artifact_uri
    (output_dir / "serverless_result.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not _completed(output_dir):
        raise ValueError("Pacote Serverless sem middle JSON válido.")


def _completed(output_dir: Path) -> bool:
    middle_paths = list(output_dir.rglob("*_middle.json"))
    if len(middle_paths) != 1:
        return False
    try:
        payload = json.loads(middle_paths[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return any(
        isinstance(payload.get(key), list)
        for key in ("pdf_info", "pages", "page_info")
    ) or any(
        key in payload
        for key in ("para_blocks", "discarded_blocks", "preproc_blocks")
    )


def _load_manifest(path: Path) -> list[WorkItem]:
    if not path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {path}")
    manifest = pd.read_csv(path)
    required = {"document_id", "sha256", "path", "filename", "page_count"}
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Colunas ausentes no manifesto: {sorted(missing)}")
    if "status" in manifest.columns:
        manifest = manifest[manifest["status"].astype(str).eq("ok")]
    manifest = (
        manifest.drop_duplicates("sha256", keep="first")
        .sort_values("sha256", kind="stable")
        .reset_index(drop=True)
    )
    items: list[WorkItem] = []
    for position, row in manifest.iterrows():
        pdf_path = Path(str(row["path"])).expanduser().resolve()
        document = DocumentRecord(
            sha256=str(row["sha256"]),
            document_id=str(row["document_id"]),
            path=pdf_path,
            filename=str(row["filename"]),
            size_bytes=pdf_path.stat().st_size if pdf_path.exists() else None,
            page_count=_as_int(row.get("page_count"), 0) or None,
        )
        items.append(
            WorkItem(
                position=int(position),
                document=document,
                output_dir=(
                    settings.mineru_output_dir
                    / "documents"
                    / document.document_id
                ),
                row=row.to_dict(),
            )
        )
    if not items:
        raise RuntimeError("Manifesto vazio.")
    return items


def pending_count(path: Path) -> int:
    """Conta artefatos ausentes/inválidos sem iniciar capacidade GPU."""
    manifests = ManifestStore(settings.mineru_output_dir / "manifests")
    return sum(
        settings.mineru_overwrite
        or (
            not _completed(config_item.output_dir)
            and manifests.load(config_item).status != "ok"
        )
        for config_item in _load_manifest(path)
    )


def _write_frame_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _reconcile_manifests(
    items: list[WorkItem],
    manifests: ManifestStore,
    output_root: Path,
) -> pd.DataFrame:
    """Reconstrói o relatório final exclusivamente dos estados duráveis."""
    rows = [
        {
            **item.row,
            **manifests.load(item).model_dump(mode="json"),
            "document_position": item.position,
        }
        for item in items
    ]
    frame = pd.DataFrame(rows).sort_values("document_position")
    _write_frame_atomic(frame, output_root / "reconciliation.csv")
    return frame


def _write_reconciliation_summary(
    frame: pd.DataFrame,
    output_root: Path,
) -> dict[str, Any]:
    """Resume o estado remoto confirmado nos manifestos duráveis."""
    statuses = (
        frame["status"].fillna("pending").astype(str).value_counts().to_dict()
        if "status" in frame
        else {}
    )
    artifacts = [
        artifact
        for values in frame.get("artifacts", pd.Series(dtype=object))
        if isinstance(values, list)
        for artifact in values
        if isinstance(artifact, dict)
    ]
    artifact_hashes = [
        str(artifact["sha256"])
        for artifact in artifacts
        if artifact.get("sha256")
    ]
    summary = {
        "manifest_count": int(len(frame)),
        "status_counts": {str(status): int(count) for status, count in statuses.items()},
        "remote_artifact_uri_count": int(
            frame.get("artifact_uri", pd.Series(dtype=object)).notna().sum()
        ),
        "artifact_count": len(artifacts),
        "artifact_hash_count": len(artifact_hashes),
        "unique_artifact_hash_count": len(set(artifact_hashes)),
        "artifacts_without_hash_count": len(artifacts) - len(artifact_hashes),
        "reconciliation_path": str(
            (output_root / "reconciliation.csv").resolve()
        ),
    }
    _write_json_atomic(output_root / "reconciliation_summary.json", summary)
    return summary


def _process(
    item: WorkItem,
    config: ExtractionConfig,
    stop_event: threading.Event,
) -> ExtractionResult:
    document = item.document
    if not document.path.exists():
        result = ExtractionResult(
            sha256=document.sha256,
            document_id=document.document_id,
            status="error",
            output_dir=item.output_dir,
            error="Arquivo PDF não encontrado.",
        )
        manifest_values = result.model_dump(mode="python")
        manifest_values.pop("throughput_eligible")
        config.manifests.update(item, **manifest_values)
        return result
    endpoint: ApiEndpoint | None = None
    saved = config.manifests.load(item)
    task_id = saved.task_id
    original_api_url = saved.api_url.rstrip("/") if saved.api_url else None
    submission_required = saved.status == "orphaned"
    task_history = list(saved.task_history)
    duration: float | None = None
    source_uri: str | None = None
    artifact_uri: str | None = None
    persisted_artifacts: list[dict[str, Any]] = []
    attempts = 0
    controller: dict[str, Any] = dict(saved.controller)
    throughput_eligible = False
    try:
        retrying = Retrying(
            stop=stop_after_attempt(config.retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            # A identidade determinística torna falhas de observação seguras
            # para retry: antes de qualquer novo POST consultamos a mesma
            # task_id no router e no índice persistido.
            retry=retry_if_exception(
                lambda error: (
                    not isinstance(error, ExtractionStopped)
                    and (
                        isinstance(error, TaskRecoveryError)
                        or not isinstance(
                            error,
                            (ResultDownloadError, TaskRequestError),
                        )
                    )
                )
            ),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                attempts = attempt.retry_state.attempt_number
                if task_id and not original_api_url:
                    raise TaskRecoveryError(
                        "Manifesto com task_id sem api_url original; "
                        "não é seguro reenviar a tarefa."
                    )
                endpoint = (
                    config.endpoint_registry.acquire_preferred(
                        original_api_url,
                        fallback_if_missing=True,
                        stop_event=stop_event,
                    )
                    if task_id and original_api_url
                    else config.endpoint_registry.acquire_for_reconciliation(
                        stop_event
                    )
                    if task_id
                    else config.endpoint_registry.acquire(stop_event)
                )
                reporter.task_started(
                    endpoint.key,
                    first_attempt=attempts == 1,
                )
                try:
                    started = time.perf_counter()
                    if (
                        not task_id
                        and not submission_required
                        and endpoint.serverless_client is None
                    ):
                        persisted_record = _reconcile_submission(
                            endpoint.api_url,
                            document.sha256,
                        )
                        if persisted_record is not None:
                            candidate_id = persisted_record["task_id"]
                            candidate_status = str(
                                persisted_record.get("status", "")
                            ).casefold()
                            known_terminal_ids = {
                                str(entry.get("task_id"))
                                for entry in task_history
                            }
                            if not (
                                candidate_status
                                in {"failed", "error", "cancelled"}
                                and candidate_id in known_terminal_ids
                            ):
                                task_id = candidate_id
                                saved = config.manifests.update(
                                    item,
                                    status="submitted",
                                    pod_id=endpoint.pod_id,
                                    api_url=endpoint.api_url,
                                    task_id=task_id,
                                    correlation_key=document.sha256,
                                    error=None,
                                )
                                original_api_url = endpoint.api_url
                    if endpoint.serverless_client is not None:
                        throughput_eligible = True
                        if config.object_storage is not None:
                            source_uri, file_url = (
                                config.object_storage.source_location(document)
                            )
                            result = endpoint.serverless_client.parse_document(
                                file_url=file_url,
                                backend=settings.mineru_backend,
                                formula_enable=True,
                                table_enable=True,
                                transport="s3",
                                basename=document.document_id,
                                timeout=max(
                                    1,
                                    int(settings.mineru_task_timeout_seconds),
                                ),
                            )
                            artifact_uri = (
                                config.object_storage.artifact_uri(result)
                            )
                        else:
                            input_limit = (
                                settings.runpod_serverless_inline_input_mb
                                * 1024
                                * 1024
                            )
                            if (
                                document.size_bytes is not None
                                and document.size_bytes > input_limit
                            ):
                                raise ValueError(
                                    "PDF excede o transporte inline "
                                    "Serverless "
                                    f"({settings.runpod_serverless_inline_input_mb} MB)."
                                )
                            result = MineruClient.parse_document_from_file(
                                endpoint.serverless_client,
                                document.path,
                                backend=settings.mineru_backend,
                                formula_enable=True,
                                table_enable=True,
                                transport="tarball_b64",
                                formats=(
                                    "markdown",
                                    "content_list",
                                    "middle",
                                    "images",
                                ),
                                basename=document.document_id,
                                timeout=max(
                                    1,
                                    int(settings.mineru_task_timeout_seconds),
                                ),
                            )
                        _save_serverless_result(
                            result,
                            item.output_dir,
                            artifact_uri=artifact_uri,
                        )
                    else:
                        persisted: dict[str, Any] | None = None
                        if task_id and not submission_required:
                            # No Network Volume o índice é compartilhado: um
                            # pacote completo pode ter sido finalizado por
                            # qualquer pod. Com Volume Disk, só o endpoint
                            # original é consultado para recuperação.
                            persisted_urls = [endpoint.api_url]
                            if settings.runpod_network_volume_id:
                                persisted_urls.extend(
                                    str(snapshot["api_url"]).rstrip("/")
                                    for snapshot in config.endpoint_registry.snapshot()
                                    if snapshot["healthy"]
                                    and snapshot["transport"] == "mineru-api"
                                    and snapshot["api_url"] != endpoint.api_url
                                )
                            recovered = _recover_orphaned_task(
                                original_api_url=endpoint.api_url,
                                persisted_api_urls=tuple(dict.fromkeys(persisted_urls)),
                                correlation_key=document.sha256,
                                task_id=task_id,
                            )
                            if recovered is None:
                                task_history = list(
                                    config.manifests.load(item).task_history
                                )
                                task_history.append(
                                    {
                                        "task_id": task_id,
                                        "pod_id": saved.pod_id,
                                        "api_url": original_api_url,
                                        "status": "orphaned",
                                        "finished_at": datetime_now_iso(),
                                    }
                                )
                                task_id = document.sha256
                                submission_required = True
                                config.manifests.update(
                                    item,
                                    status="orphaned",
                                    attempts=attempts,
                                    retry_count=max(0, attempts - 1),
                                    pod_id=endpoint.pod_id,
                                    api_url=endpoint.api_url,
                                    task_id=task_id,
                                    correlation_key=document.sha256,
                                    task_history=task_history,
                                    error=(
                                        "Tarefa órfã confirmada após restart "
                                        "do router; reenviando PDF."
                                    ),
                                )
                            elif isinstance(recovered, dict):
                                persisted = recovered
                        if not task_id or submission_required:
                            if item.output_dir.exists():
                                shutil.rmtree(item.output_dir)
                            task_id = task_id or document.sha256
                            config.manifests.update(
                                item,
                                status="submitting",
                                attempts=attempts,
                                retry_count=max(0, attempts - 1),
                                pod_id=endpoint.pod_id,
                                api_url=endpoint.api_url,
                                task_id=task_id,
                                correlation_key=document.sha256,
                                error=None,
                            )
                            original_api_url = endpoint.api_url
                            _submit(
                                document.path,
                                endpoint.api_url,
                                correlation_key=document.sha256,
                                task_id=task_id,
                            )
                            throughput_eligible = True
                            # A confirmação da API é persistida antes de qualquer poll.
                            saved = config.manifests.update(
                                item,
                                status="submitted",
                                attempts=attempts,
                                retry_count=max(0, attempts - 1),
                                pod_id=endpoint.pod_id,
                                api_url=endpoint.api_url,
                                task_id=task_id,
                                correlation_key=document.sha256,
                                error=None,
                            )
                            original_api_url = endpoint.api_url
                            submission_required = False
                        if persisted is None:
                            config.manifests.update(
                                item, status="waiting_persisted", task_id=task_id
                            )
                            persisted = _wait_persisted_result(
                                endpoint.api_url,
                                document.sha256,
                                task_id,
                            )
                        package_dir = str(persisted["package_dir"]).strip("/")
                        artifact_uri = f"/workspace/results/{package_dir}"
                        persisted_artifacts = list(persisted["artifacts"])
                    duration = time.perf_counter() - started
                    if throughput_eligible:
                        controller = config.endpoint_registry.record_completion(
                            endpoint,
                            pages=document.page_count or 1,
                            duration=duration,
                        )
                except ExtractionStopped:
                    raise
                except Exception as error:
                    message = f"{type(error).__name__}: {error}"
                    hardware_failure = _hardware_failure(message)
                    if hardware_failure:
                        config.endpoint_registry.mark_defective(
                            endpoint,
                            message[:240],
                        )
                    will_retry = (
                        attempts <= config.retries
                        and (
                            isinstance(error, TaskRecoveryError)
                            or not isinstance(
                                error,
                                (ResultDownloadError, TaskRequestError),
                            )
                        )
                    )
                    identity_unresolved = (
                        isinstance(error, TaskIdentityError)
                        and not error.returned_task_id
                    )
                    terminal_task = isinstance(error, TaskTerminalError)
                    manifest = config.manifests.load(item)
                    task_history = list(manifest.task_history)
                    next_task_id = task_id
                    if (
                        isinstance(error, TaskIdentityError)
                        and error.returned_task_id
                    ):
                        task_history.append(
                            {
                                "task_id": error.returned_task_id,
                                "expected_task_id": task_id,
                                "pod_id": endpoint.pod_id,
                                "api_url": endpoint.api_url,
                                "status": "identity_mismatch",
                                "error": message,
                                "finished_at": datetime_now_iso(),
                            }
                        )
                        # A resposta prova que esse ID foi aceito. Preserve-o
                        # para recuperar a tarefa legada sem um segundo POST.
                        next_task_id = error.returned_task_id
                    if terminal_task and task_id:
                        task_history.append(
                            {
                                "task_id": task_id,
                                "pod_id": endpoint.pod_id,
                                "api_url": endpoint.api_url,
                                "status": "failed",
                                "error": message,
                                "finished_at": datetime_now_iso(),
                            }
                        )
                        if will_retry:
                            next_task_id = None
                    config.manifests.update(
                        item,
                        status=(
                            "identity_unresolved"
                            if identity_unresolved
                            else "retry"
                            if will_retry
                            else "recoverable"
                            if isinstance(error, ResultDownloadError)
                            else "error"
                        ),
                        attempts=attempts,
                        retry_count=max(0, attempts - 1),
                        pod_id=endpoint.pod_id,
                        api_url=endpoint.api_url,
                        task_id=next_task_id,
                        correlation_key=document.sha256,
                        task_history=task_history,
                        error=message,
                    )
                    if (
                        _memory_pressure_failure(message)
                        and not hardware_failure
                    ):
                        config.endpoint_registry.reduce_capacity(
                            endpoint,
                            "pressão de memória",
                        )
                    if will_retry:
                        reporter.retry(endpoint.key)
                    task_id = next_task_id
                    raise
                finally:
                    reporter.task_released(endpoint.key)
                    config.endpoint_registry.release(endpoint)
        result = ExtractionResult(
            sha256=document.sha256,
            document_id=document.document_id,
            status="ok",
            output_dir=item.output_dir,
            attempts=attempts,
            retry_count=max(0, attempts - 1),
            pod_id=endpoint.pod_id if endpoint else None,
            api_url=endpoint.api_url if endpoint else None,
            task_id=task_id,
            duration_seconds=round(duration or 0.0, 3),
            source_uri=source_uri,
            artifact_uri=artifact_uri,
            artifacts=persisted_artifacts,
            task_history=task_history,
            throughput_eligible=throughput_eligible,
        )
        manifest_values = result.model_dump(mode="python")
        manifest_values.pop("throughput_eligible")
        config.manifests.update(
            item,
            **manifest_values,
            controller=controller,
        )
        return result
    except ExtractionStopped:
        raise
    except Exception as error:
        status = (
            "identity_unresolved"
            if isinstance(error, TaskIdentityError)
            and not error.returned_task_id
            else "recoverable"
            if isinstance(error, ResultDownloadError)
            else "error"
        )
        result = ExtractionResult(
            sha256=document.sha256,
            document_id=document.document_id,
            status=status,
            output_dir=item.output_dir,
            attempts=attempts,
            retry_count=max(0, attempts - 1),
            pod_id=endpoint.pod_id if endpoint else None,
            api_url=endpoint.api_url if endpoint else None,
            task_id=task_id,
            duration_seconds=duration,
            source_uri=source_uri,
            artifact_uri=artifact_uri,
            artifacts=persisted_artifacts,
            task_history=task_history,
            throughput_eligible=throughput_eligible,
            error=f"{type(error).__name__}: {error}",
        )
        manifest_values = result.model_dump(mode="python")
        manifest_values.pop("throughput_eligible")
        config.manifests.update(item, **manifest_values)
        return result


async def _run_pending(
    config: ExtractionConfig,
    stop_event: threading.Event,
    pending: deque[WorkItem],
    results: list[dict[str, Any]],
) -> None:
    """Executa a fila limitada com concorrência ajustável em runtime."""
    initial_capacity = max(1, config.endpoint_registry.total_capacity)
    admission = anyio.CapacityLimiter(initial_capacity)
    worker_threads = anyio.CapacityLimiter(4096)
    send, receive = anyio.create_memory_object_stream[WorkItem](
        max_buffer_size=max(1, initial_capacity * 2),
    )
    finished = anyio.Event()

    async def process_item(item: WorkItem, borrower: object) -> None:
        try:
            try:
                result = await anyio.to_thread.run_sync(
                    _process,
                    item,
                    config,
                    stop_event,
                    limiter=worker_threads,
                )
            except ExtractionStopped:
                pending.append(item)
                return
            reporter.document_finished(
                status=result.status,
                pod_key=result.pod_id or result.api_url,
                error=result.error,
                sha256=result.sha256,
                pages=(
                    item.document.page_count
                    if result.throughput_eligible
                    else None
                ),
            )
            results.append(
                {
                    **item.row,
                    **result.model_dump(mode="json"),
                    "document_position": item.position,
                }
            )
        finally:
            admission.release_on_behalf_of(borrower)

    async def produce() -> None:
        async with send:
            while pending and not stop_event.is_set():
                await send.send(pending.popleft())

    async def consume() -> None:
        async with receive:
            async with anyio.create_task_group() as tasks:
                async for item in receive:
                    while (
                        config.endpoint_registry.total_capacity <= 0
                        and not stop_event.is_set()
                    ):
                        await anyio.sleep(0.25)
                    if stop_event.is_set():
                        pending.append(item)
                        continue
                    borrower = object()
                    await admission.acquire_on_behalf_of(borrower)
                    if stop_event.is_set():
                        admission.release_on_behalf_of(borrower)
                        pending.append(item)
                        continue
                    tasks.start_soon(process_item, item, borrower)
        finished.set()

    async def synchronize_capacity() -> None:
        while not finished.is_set():
            desired = max(
                1,
                config.endpoint_registry.total_capacity,
            )
            if admission.total_tokens != desired:
                admission.total_tokens = desired
            with anyio.move_on_after(0.25):
                await finished.wait()

    async def refresh_health() -> None:
        while not finished.is_set():
            with anyio.move_on_after(10):
                await finished.wait()
            if finished.is_set():
                return
            await anyio.to_thread.run_sync(
                config.endpoint_registry.refresh_health,
            )

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(synchronize_capacity)
        tasks.start_soon(refresh_health)
        tasks.start_soon(consume)
        tasks.start_soon(produce)


def _execute(
    config: ExtractionConfig,
    stop_event: threading.Event,
) -> dict[str, Any]:
    items = _load_manifest(config.manifest_path)
    config.output_root.mkdir(parents=True, exist_ok=True)

    deferred = [
        item
        for item in items
        if config.max_source_bytes is not None
        and item.document.size_bytes is not None
        and item.document.size_bytes > config.max_source_bytes
    ]
    if deferred:
        deferred_ids = {
            item.document.document_id
            for item in deferred
        }
        items = [
            item
            for item in items
            if item.document.document_id not in deferred_ids
        ]
        reporter.event(
            "Transporte direto | "
            f"elegíveis={len(items)} | "
            f"aguardando bucket={len(deferred)}",
            color="cyan",
        )

    reporter.start_progress(len(items))

    pending_items: list[WorkItem] = []
    deferred_error_items: list[WorkItem] = []
    results: list[dict[str, Any]] = []
    reused = 0
    for item in items:
        persisted = config.manifests.load(item)
        if (
            (_completed(item.output_dir) or persisted.status == "ok")
            and not config.overwrite
        ):
            reused += 1
            result = ExtractionResult(
                sha256=item.document.sha256,
                document_id=item.document.document_id,
                status="ok",
                output_dir=item.output_dir,
                pod_id=persisted.pod_id,
                api_url=persisted.api_url,
                task_id=persisted.task_id,
                correlation_key=persisted.correlation_key,
                duration_seconds=persisted.duration_seconds,
                source_uri=persisted.source_uri,
                artifact_uri=persisted.artifact_uri,
                artifacts=persisted.artifacts,
                error=persisted.error,
            )
            results.append(
                {
                    **item.row,
                    **result.model_dump(mode="json"),
                    "document_position": item.position,
                    "status": "skipped",
                }
            )
        elif persisted.status == "identity_unresolved":
            result = ExtractionResult(
                sha256=item.document.sha256,
                document_id=item.document.document_id,
                status="error",
                output_dir=item.output_dir,
                attempts=persisted.attempts,
                retry_count=persisted.retry_count,
                pod_id=persisted.pod_id,
                api_url=persisted.api_url,
                task_id=persisted.task_id,
                correlation_key=persisted.correlation_key,
                task_history=persisted.task_history,
                error=persisted.error,
            )
            results.append(
                {
                    **item.row,
                    **result.model_dump(mode="json"),
                    "document_position": item.position,
                }
            )
            reporter.document_finished(
                status="error",
                pod_key=persisted.pod_id or persisted.api_url,
                error=persisted.error,
                sha256=item.document.sha256,
            )
        else:
            target = (
                deferred_error_items
                if persisted.status == "error"
                else pending_items
            )
            target.append(item)
    pending: deque[WorkItem] = deque(
        (*pending_items, *deferred_error_items)
    )
    if deferred_error_items:
        reporter.event(
            "Erros anteriores adiados para o fim da fila | "
            f"documentos={len(deferred_error_items)}",
            color="yellow",
        )
    reporter.restore_reused(reused)

    startup_deadline = (
        time.monotonic() + settings.runpod_startup_timeout_seconds
    )
    while pending and not config.endpoint_registry.wait_for_first(0.5):
        if stop_event.is_set():
            break
        if time.monotonic() >= startup_deadline:
            raise TimeoutError(
                "Nenhum pod MinerU ficou pronto dentro do limite."
            )

    started = time.perf_counter()
    anyio.run(
        _run_pending,
        config,
        stop_event,
        pending,
        results,
    )
    if stop_event.is_set():
        reporter.request_stop()

    runs_df = pd.DataFrame(results)
    if not runs_df.empty:
        runs_df = runs_df.sort_values("document_position")
    _write_frame_atomic(runs_df, config.output_root / "runs.csv")
    errors_df = (
        runs_df[~runs_df["status"].isin(("ok", "skipped"))]
        if not runs_df.empty
        else runs_df
    )
    _write_frame_atomic(errors_df, config.output_root / "errors.csv")
    reconciled = _reconcile_manifests(
        items + deferred,
        config.manifests,
        config.output_root,
    )
    reconciliation_summary = _write_reconciliation_summary(
        reconciled,
        config.output_root,
    )
    elapsed = time.perf_counter() - started
    new_completed_pages = sum(
        _as_int(row.get("page_count"), 0)
        for row in results
        if row.get("status") == "ok" and row.get("throughput_eligible")
    )
    reconciled_pages = sum(
        _as_int(row.get("page_count"), 0)
        for row in results
        if row.get("status") == "ok" and not row.get("throughput_eligible")
    )
    new_completed_documents = sum(
        row.get("status") == "ok" and row.get("throughput_eligible")
        for row in results
    )
    reconciled_documents = sum(
        row.get("status") == "ok" and not row.get("throughput_eligible")
        for row in results
    )
    completed_documents = new_completed_documents + reconciled_documents
    summary = {
        "run_id": config.run_id,
        "manifest_count": len(items) + len(deferred),
        "eligible_count": len(items),
        "deferred_for_bucket_count": len(deferred),
        "ok_count": completed_documents,
        "completed_pages": new_completed_pages + reconciled_pages,
        "new_completed_pages": new_completed_pages,
        "reconciled_pages": reconciled_pages,
        "new_completed_documents": new_completed_documents,
        "reconciled_documents": reconciled_documents,
        "pages_per_minute": round(
            new_completed_pages * 60 / max(elapsed, 0.001),
            2,
        ),
        "documents_per_minute": round(
            new_completed_documents * 60 / max(elapsed, 0.001),
            2,
        ),
        "reused_count": reused,
        "error_count": sum(row["status"] == "error" for row in results),
        "recoverable_count": sum(
            row["status"] == "recoverable" for row in results
        ),
        "submission_uncertain_count": sum(
            row["status"] == "submission_uncertain" for row in results
        ),
        "retry_count": sum(
            int(row.get("retry_count") or 0) for row in results
        ),
        "remaining_count": len(pending),
        "reconciled_count": len(reconciled),
        "reconciliation": reconciliation_summary,
        "stopped_early": stop_event.is_set(),
        "pod_count": config.endpoint_registry.endpoint_count,
        "client_capacity": config.endpoint_registry.total_capacity,
        "elapsed_seconds": round(elapsed, 3),
    }
    _write_json_atomic(config.output_root / "summary.json", summary)
    _write_json_atomic(
        config.output_root / "pods.json",
        config.endpoint_registry.snapshot(),
    )
    reporter.event(
        "Resumo | "
        f"concluídos={summary['ok_count']} | "
        f"reutilizados={summary['reused_count']} | "
        f"erros={summary['error_count']} | "
        f"restantes={summary['remaining_count']} | "
        f"vazão={summary['pages_per_minute']} pág/min",
        color="green" if not summary["error_count"] else "yellow",
    )
    return summary


def extract(
    *,
    endpoint_registry: ApiEndpointRegistry | None = None,
    api_urls: tuple[str, ...] = (),
    manifest_path: Path | None = None,
    stop_event: threading.Event | None = None,
    run_id: str | None = None,
    max_source_bytes: int | None = None,
    object_storage: ObjectStorage | None = None,
) -> dict[str, Any]:
    registry = endpoint_registry or ApiEndpointRegistry(
        settings.mineru_concurrency_per_pod
    )
    for api_url in api_urls:
        registry.add(api_url)
    config = ExtractionConfig(
        endpoint_registry=registry,
        manifest_path=manifest_path or settings.inventory_path,
        output_root=settings.mineru_output_dir,
        retries=settings.mineru_retries,
        overwrite=settings.mineru_overwrite,
        run_id=run_id or uuid.uuid4().hex,
        manifests=ManifestStore(settings.mineru_output_dir / "manifests"),
        max_source_bytes=max_source_bytes,
        object_storage=object_storage,
    )
    return _execute(config, stop_event or threading.Event())
