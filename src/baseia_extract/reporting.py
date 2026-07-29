from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass(slots=True)
class PodStats:
    label: str
    gpu: str = "-"
    health: str = "iniciando"
    service_capacity: int = 0
    client_capacity: int = 0
    in_flight: int = 0
    completed: int = 0
    retries: int = 0
    errors: int = 0
    api_queued: int = 0
    pages_per_minute: float | None = None
    documents_per_minute: float | None = None
    p50_seconds: float | None = None
    p95_seconds: float | None = None
    circuit: str = "fechado"
    gpu_usage: tuple[int, ...] = ()
    vram_usage: tuple[int, ...] = ()
    cpu_usage: int | None = None
    ram_usage: int | None = None

    @property
    def idle(self) -> int:
        return max(0, self.client_capacity - self.in_flight)


class ExtractionReporter:
    """Painel agregado e log textual, sem nomes de documentos."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._console = Console()
        self._live: Live | None = None
        self._logger = logging.getLogger("baseia.extract")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.addHandler(logging.NullHandler())
        self._total = 0
        self._pending = 0
        self._completed = 0
        self._completed_pages = 0
        self._reused = 0
        self._retries = 0
        self._errors = 0
        self._in_flight = 0
        self._stopping = False
        self._pods: dict[str, PodStats] = {}
        self._events: deque[tuple[str, str, str, str]] = deque(maxlen=5)
        self._last_snapshot = 0.0
        self._started_at: float | None = None

    def configure(self, log_path: Path) -> None:
        with self._lock:
            self.close()
            self._events.clear()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s"
                )
            )
            self._logger.handlers.clear()
            self._logger.addHandler(handler)

    def close(self) -> None:
        with self._lock:
            if self._live is not None:
                self._live.stop()
                self._live = None
            for handler in tuple(self._logger.handlers):
                handler.close()
                self._logger.removeHandler(handler)
            self._logger.addHandler(logging.NullHandler())

    def event(
        self,
        message: str,
        *,
        level: str = "INFO",
        color: str | None = None,
        terminal: bool = True,
    ) -> None:
        with self._lock:
            getattr(self._logger, level.lower(), self._logger.info)(message)
            if terminal:
                style = color or {
                    "ERROR": "red",
                    "WARNING": "yellow",
                }.get(level.upper(), "white")
                self._events.append(
                    (
                        time.strftime("%H:%M:%S"),
                        level.upper(),
                        message.replace("\n", " "),
                        style,
                    )
                )
                self._refresh()

    def start_progress(self, total: int) -> None:
        with self._lock:
            self._total = total
            self._pending = total
            self._completed = 0
            self._completed_pages = 0
            self._reused = 0
            self._retries = 0
            self._errors = 0
            self._in_flight = 0
            self._stopping = False
            self._started_at = time.monotonic()
            self._live = Live(
                self._render(),
                console=self._console,
                refresh_per_second=4,
                transient=False,
            )
            self._live.start()
            self._write_snapshot(force=True)

    def restore_reused(self, count: int) -> None:
        with self._lock:
            self._reused = count
            self._pending = max(0, self._pending - count)
            self._refresh()

    def register_pod(
        self,
        pod_key: str,
        *,
        label: str,
        gpu: str | None,
        service_capacity: int,
        client_capacity: int,
        api_queued: int = 0,
    ) -> None:
        with self._lock:
            self._pods[pod_key] = PodStats(
                label=label,
                gpu=gpu or "-",
                health="pronto",
                service_capacity=service_capacity,
                client_capacity=client_capacity,
                api_queued=api_queued,
            )
            self._refresh()

    def update_health(
        self,
        pod_key: str,
        *,
        healthy: bool,
        api_queued: int = 0,
        service_capacity: int | None = None,
    ) -> None:
        with self._lock:
            pod = self._pods.get(pod_key)
            if pod is None:
                return
            pod.health = "pronto" if healthy else "indisponível"
            pod.api_queued = api_queued
            if service_capacity is not None:
                pod.service_capacity = service_capacity
            self._refresh()

    def update_capacity(
        self,
        pod_key: str,
        capacity: int,
        *,
        draining: bool = False,
    ) -> None:
        with self._lock:
            pod = self._pods.get(pod_key)
            if pod is None:
                return
            pod.client_capacity = capacity
            if draining:
                pod.health = "drenando"
            elif pod.health == "drenando":
                pod.health = "pronto"
            self._refresh()

    def update_resources(
        self,
        pod_key: str,
        *,
        gpu: tuple[int, ...],
        vram: tuple[int, ...],
        cpu: int,
        ram: int,
    ) -> None:
        with self._lock:
            pod = self._pods.get(pod_key)
            if pod is None:
                return
            pod.gpu_usage = gpu
            pod.vram_usage = vram
            pod.cpu_usage = cpu
            pod.ram_usage = ram
            self._refresh()

    def update_throughput(
        self,
        pod_key: str,
        *,
        pages_per_minute: float,
        documents_per_minute: float,
        p50_seconds: float,
        p95_seconds: float,
    ) -> None:
        with self._lock:
            pod = self._pods.get(pod_key)
            if pod is None:
                return
            pod.pages_per_minute = pages_per_minute
            pod.documents_per_minute = documents_per_minute
            pod.p50_seconds = p50_seconds
            pod.p95_seconds = p95_seconds
            self._refresh()

    def update_circuit(self, pod_key: str, circuit: str) -> None:
        with self._lock:
            pod = self._pods.get(pod_key)
            if pod is None:
                return
            pod.circuit = circuit
            self._refresh()

    def task_started(
        self,
        pod_key: str,
        *,
        first_attempt: bool,
    ) -> None:
        with self._lock:
            pod = self._pods[pod_key]
            pod.in_flight += 1
            self._in_flight += 1
            if first_attempt:
                self._pending = max(0, self._pending - 1)
            self._refresh()

    def task_released(self, pod_key: str) -> None:
        with self._lock:
            pod = self._pods[pod_key]
            pod.in_flight = max(0, pod.in_flight - 1)
            self._in_flight = max(0, self._in_flight - 1)
            self._refresh()

    def retry(self, pod_key: str) -> None:
        with self._lock:
            self._retries += 1
            self._pods[pod_key].retries += 1
            self._refresh()

    def document_finished(
        self,
        *,
        status: str,
        pod_key: str | None = None,
        error: str | None = None,
        sha256: str | None = None,
        pages: int | None = None,
    ) -> None:
        with self._lock:
            if status == "ok":
                self._completed += 1
                if pages is not None and pages > 0:
                    self._completed_pages += pages
                if pod_key in self._pods:
                    self._pods[pod_key].completed += 1
            elif status == "reused":
                self._reused += 1
            else:
                self._errors += 1
                if pod_key in self._pods:
                    self._pods[pod_key].errors += 1
                self._logger.error(
                    "extração falhou sha256=%s erro=%s",
                    (sha256 or "-")[:16],
                    (error or "-").replace("\n", " ")[:1000],
                )
            self._refresh()

    def request_stop(self) -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._logger.warning(
                "Encerramento solicitado; drenando trabalhos em voo."
            )
            self._events.append(
                (
                    time.strftime("%H:%M:%S"),
                    "WARNING",
                    "Encerrando novos envios; aguardando trabalhos em voo.",
                    "yellow",
                )
            )
            self._refresh()

    def _render(self) -> Group:
        work = Table(title="Trabalho", expand=True)
        work.add_column("Pod", style="cyan", no_wrap=True)
        work.add_column("Estado/Circuito", no_wrap=True)
        work.add_column("Cliente/API", justify="right", no_wrap=True)
        work.add_column("Voo/Ocioso", justify="right", no_wrap=True)
        work.add_column("OK/R/E", justify="right", no_wrap=True)
        work.add_column("Fila", justify="right")
        work.add_column(
            "Pág/min · p95",
            justify="right",
            style="green",
            no_wrap=True,
        )

        pressure = Table(title="Pressão", expand=True)
        pressure.add_column("Pod", style="cyan", no_wrap=True)
        pressure.add_column("GPU média/máx", justify="right", no_wrap=True)
        pressure.add_column("VRAM média/máx", justify="right", no_wrap=True)
        pressure.add_column("CPU", justify="right")
        pressure.add_column("RAM", justify="right")

        if self._pods:
            for pod in self._pods.values():
                work.add_row(
                    pod.label,
                    f"{pod.health}/{pod.circuit}",
                    f"{pod.client_capacity}/{pod.service_capacity}",
                    f"{pod.in_flight}/{pod.idle}",
                    f"{pod.completed}/{pod.retries}/{pod.errors}",
                    str(pod.api_queued),
                    f"{self._rate(pod.pages_per_minute)} · "
                    f"{self._seconds(pod.p95_seconds)}",
                )
                pressure.add_row(
                    pod.label,
                    self._average_and_max(pod.gpu_usage),
                    self._average_and_max(pod.vram_usage),
                    self._percentage(pod.cpu_usage),
                    self._percentage(pod.ram_usage),
                )
        else:
            work.add_row(
                "aguardando",
                "iniciando",
                "0/0",
                "0/0",
                "0/0/0",
                "0",
                "- · -",
            )
            pressure.add_row(
                "aguardando",
                "-",
                "-",
                "-",
                "-",
            )

        state = "ENCERRANDO" if self._stopping else "EXECUTANDO"
        capacity = sum(pod.client_capacity for pod in self._pods.values())
        idle = sum(pod.idle for pod in self._pods.values())
        pages_per_minute = sum(
            pod.pages_per_minute or 0.0 for pod in self._pods.values()
        )
        documents_per_minute = sum(
            pod.documents_per_minute or 0.0 for pod in self._pods.values()
        )
        elapsed_minutes = max(
            (time.monotonic() - self._started_at) / 60,
            1 / 60,
        ) if self._started_at is not None else 1 / 60
        average_pages_per_minute = self._completed_pages / elapsed_minutes
        summary = "\n".join(
            (
                f"[bold]{state}[/bold]  total={self._total}  "
                f"[green]concluídos={self._completed}[/green]  "
                f"reutilizados={self._reused}  pendentes={self._pending}",
                f"em voo={self._in_flight}  "
                f"[yellow]retries={self._retries}[/yellow]  "
                f"[red]erros={self._errors}[/red]  pods={len(self._pods)}  "
                f"capacidade={capacity}  ociosa={idle}",
                f"[green]vazão={pages_per_minute:.1f} pág/min[/green]  "
                f"média={average_pages_per_minute:.1f} pág/min  "
                f"{documents_per_minute:.1f} docs/min",
            )
        )
        sections: list[object] = [
            work,
            pressure,
            Panel(summary, title="Extração MinerU"),
        ]
        if self._events:
            events = Table(
                title="Eventos recentes",
                expand=True,
                show_header=False,
                box=None,
                padding=(0, 1),
            )
            events.add_column("Hora", style="dim", no_wrap=True)
            events.add_column("Nível", no_wrap=True)
            events.add_column("Evento", overflow="ellipsis")
            for timestamp, level, message, style in self._events:
                events.add_row(
                    timestamp,
                    Text(level, style=style),
                    Text(message, style=style),
                )
            sections.append(events)
        return Group(*sections)

    def _write_snapshot(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_snapshot < 10:
            return
        self._last_snapshot = now
        capacity = sum(pod.client_capacity for pod in self._pods.values())
        idle = sum(pod.idle for pod in self._pods.values())
        pages_per_minute = sum(
            pod.pages_per_minute or 0.0 for pod in self._pods.values()
        )
        documents_per_minute = sum(
            pod.documents_per_minute or 0.0 for pod in self._pods.values()
        )
        elapsed_minutes = max(
            (time.monotonic() - self._started_at) / 60,
            1 / 60,
        ) if self._started_at is not None else 1 / 60
        average_pages_per_minute = self._completed_pages / elapsed_minutes
        self._logger.info(
            "estado total=%d concluidos=%d reutilizados=%d em_voo=%d "
            "retries=%d erros=%d pendentes=%d pods=%d capacidade=%d "
            "ociosa=%d paginas=%d paginas_min=%.2f "
            "paginas_min_media=%.2f docs_min=%.2f",
            self._total,
            self._completed,
            self._reused,
            self._in_flight,
            self._retries,
            self._errors,
            self._pending,
            len(self._pods),
            capacity,
            idle,
            self._completed_pages,
            pages_per_minute,
            average_pages_per_minute,
            documents_per_minute,
        )
        for pod in self._pods.values():
            self._logger.info(
                "pod=%s saude=%s cliente=%d api=%d em_voo=%d "
                "ocioso=%d concluidos=%d retries=%d erros=%d fila_api=%d "
                "gpu=%s vram=%s cpu=%s ram=%s paginas_min=%s docs_min=%s "
                "p50_s=%s p95_s=%s circuito=%s",
                pod.label,
                pod.health,
                pod.client_capacity,
                pod.service_capacity,
                pod.in_flight,
                pod.idle,
                pod.completed,
                pod.retries,
                pod.errors,
                pod.api_queued,
                self._percentages(pod.gpu_usage),
                self._percentages(pod.vram_usage),
                self._percentage(pod.cpu_usage),
                self._percentage(pod.ram_usage),
                self._rate(pod.pages_per_minute),
                self._rate(pod.documents_per_minute),
                self._seconds(pod.p50_seconds),
                self._seconds(pod.p95_seconds),
                pod.circuit,
            )

    @staticmethod
    def _percentage(value: int | None) -> str:
        return "-" if value is None else f"{value}%"

    @staticmethod
    def _percentages(values: tuple[int, ...]) -> str:
        return "/".join(f"{value}%" for value in values) if values else "-"

    @staticmethod
    def _average_and_max(values: tuple[int, ...]) -> str:
        if not values:
            return "-"
        return f"{sum(values) / len(values):.0f}%/{max(values)}%"

    @staticmethod
    def _rate(value: float | None) -> str:
        return "-" if value is None else f"{value:.1f}"

    @staticmethod
    def _seconds(value: float | None) -> str:
        return "-" if value is None else f"{value:.1f}s"

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render(), refresh=True)
        self._write_snapshot()


reporter = ExtractionReporter()
