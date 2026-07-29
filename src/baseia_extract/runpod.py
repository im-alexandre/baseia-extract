from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
from runpod.api.graphql import run_graphql_query

from .reporting import reporter
from .settings import settings


@dataclass(frozen=True, slots=True)
class ManagedPod:
    pod_id: str
    name: str
    api_url: str
    gpu_id: str | None = None
    source: str = "managed"
    actual_status: str | None = None
    workers: int | None = None


@dataclass(frozen=True, slots=True)
class GpuOption:
    gpu_id: str
    memory_gb: int
    stock_status: str


_WORKLOAD_MIN_VRAM_GB = {
    "computer-vision": 8,
    "data-processing": 8,
    "image-generation": 16,
    "llm-inference-small": 24,
    "llm-inference-large": 48,
    "llm-training": 40,
    "3d-rendering": 16,
}

_MINERU_HIGH_CONCURRENCY_GPUS = (
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA L40S",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
    "NVIDIA A100-SXM4-80GB",
    "NVIDIA H100 80GB HBM3",
)

_MINERU_BUDGET_GPUS = (
    "NVIDIA RTX A4000",
    "NVIDIA RTX 2000 Ada Generation",
    "NVIDIA RTX A4500",
    "NVIDIA RTX 4000 Ada Generation",
    "NVIDIA GeForce RTX 3090",
    "NVIDIA RTX A5000",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA RTX A6000",
    "NVIDIA L40",
    "NVIDIA L40S",
)

_POD_RESOURCE_QUERY = """
query {
  myself {
    pods {
      id
      runtime {
        gpus {
          gpuUtilPercent
          memoryUtilPercent
        }
        container {
          cpuPercent
          memoryPercent
        }
      }
    }
  }
}
"""


def _runpod_api_key() -> str | None:
    if value := os.getenv("RUNPOD_API_KEY", "").strip():
        return value

    config_path = Path.home() / ".runpod" / "config.toml"
    try:
        with config_path.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    default = config.get("default")
    if isinstance(default, dict):
        value = str(default.get("api_key") or "").strip()
        if value:
            return value
    return str(config.get("apikey") or "").strip() or None


def pod_resource_usage() -> dict[str, dict[str, object]]:
    """Consulta em lote a telemetria oficial dos Pods RunPod."""
    api_key = _runpod_api_key()
    if api_key is None:
        raise RuntimeError(
            "RUNPOD_API_KEY ausente e ~/.runpod/config.toml não encontrado."
        )
    payload = run_graphql_query(
        _POD_RESOURCE_QUERY,
        api_key=api_key,
    )
    pods = payload.get("data", {}).get("myself", {}).get("pods", [])
    result: dict[str, dict[str, object]] = {}
    for pod in pods:
        pod_id = str(pod.get("id") or "").strip()
        runtime = pod.get("runtime") or {}
        if not pod_id or not isinstance(runtime, dict):
            continue
        gpus = runtime.get("gpus") or []
        container = runtime.get("container") or {}
        result[pod_id] = {
            "gpu": tuple(
                int(gpu.get("gpuUtilPercent") or 0)
                for gpu in gpus
                if isinstance(gpu, dict)
            ),
            "vram": tuple(
                int(gpu.get("memoryUtilPercent") or 0)
                for gpu in gpus
                if isinstance(gpu, dict)
            ),
            "cpu": int(container.get("cpuPercent") or 0)
            if isinstance(container, dict)
            else 0,
            "ram": int(container.get("memoryPercent") or 0)
            if isinstance(container, dict)
            else 0,
        }
    return result


def _gpu_tier_rank(gpu_id: str) -> int | None:
    if settings.runpod_hardware_profile == "mineru-budget-24":
        try:
            return _MINERU_BUDGET_GPUS.index(gpu_id)
        except ValueError:
            return None
    if settings.runpod_hardware_profile in {
        "mineru-24",
        "mineru-50",
        "mineru-80",
    }:
        try:
            return _MINERU_HIGH_CONCURRENCY_GPUS.index(gpu_id)
        except ValueError:
            return None
    return 0


def effective_min_vram_gb() -> int:
    """Combina o piso do workload com o mínimo explícito do projeto."""
    workload_minimum = _WORKLOAD_MIN_VRAM_GB[settings.runpod_workload]
    return max(workload_minimum, settings.runpod_min_vram_gb)


def concurrency_for_gpu(gpu_id: str) -> int:
    """Retorna a capacidade de cada worker GPU gerenciado pelo router."""
    del gpu_id
    return max(
        1,
        math.ceil(
            settings.mineru_concurrency_per_pod
            / settings.runpod_gpu_count
        ),
    )


def _runpodctl(*args: str) -> object:
    executable = shutil.which("runpodctl")
    if executable is None:
        raise FileNotFoundError(
            "runpodctl não foi encontrado no PATH. Instale e configure o CLI do RunPod."
        )

    completed = subprocess.run(
        [executable, *args, "--output=json"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"runpodctl {' '.join(args)} falhou: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )

    payload = completed.stdout.strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Saída inválida do runpodctl: {payload[:2000]}") from error


def _as_items(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "templates", "pods", "gpus", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def resolve_template_id(template_name: str) -> str:
    """Resolve um template privado por nome exato e exige resultado único."""
    payload = _runpodctl(
        "template",
        "search",
        template_name,
        "--type=user",
        "--limit=100",
    )
    matches = [
        item
        for item in _as_items(payload)
        if str(item.get("name", "")).strip().casefold()
        == template_name.strip().casefold()
    ]
    if not matches:
        raise LookupError(f"Template RunPod não encontrado: {template_name!r}")
    if len(matches) > 1:
        ids = [str(item.get("id")) for item in matches]
        raise LookupError(
            f"Mais de um template possui o nome {template_name!r}: {ids}."
        )

    template_id = matches[0].get("id")
    if not isinstance(template_id, str) or not template_id:
        raise RuntimeError(f"Template sem ID válido: {matches[0]}")
    return template_id


def _extract_pod_id(payload: object) -> str:
    for item in _as_items(payload):
        for key in ("id", "podId", "pod_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    raise RuntimeError(f"Não foi possível obter o ID do pod: {payload}")


def available_gpus(min_vram_gb: int) -> tuple[GpuOption, ...]:
    """Lista GPUs disponíveis que atendem ao mínimo de VRAM."""
    payload = _runpodctl("gpu", "list")
    options: list[GpuOption] = []

    for item in _as_items(payload):
        gpu_id = item.get("gpuId") or item.get("id")
        memory = item.get("memoryInGb") or item.get("memory_in_gb")
        available = item.get("available", True)
        if not isinstance(gpu_id, str) or not gpu_id:
            continue
        try:
            memory_gb = int(float(str(memory)))
        except (TypeError, ValueError):
            continue
        if available is False or memory_gb < min_vram_gb:
            continue
        if _gpu_tier_rank(gpu_id) is None:
            continue
        options.append(
            GpuOption(
                gpu_id=gpu_id,
                memory_gb=memory_gb,
                stock_status=str(item.get("stockStatus", "")).strip(),
            )
        )

    stock_rank = {"high": 0, "medium": 1, "low": 2}
    options.sort(
        key=lambda option: (
            _gpu_tier_rank(option.gpu_id) or 0,
            stock_rank.get(option.stock_status.casefold(), 3),
            option.memory_gb,
            option.gpu_id,
        )
    )
    if not options:
        raise RuntimeError(
            "Nenhuma GPU disponível atende a "
            f"RUNPOD_MIN_VRAM_GB={min_vram_gb}."
        )
    return tuple(options)


def create_pod(
    *,
    template_id: str,
    index: int,
    gpu_options: tuple[GpuOption, ...],
) -> ManagedPod:
    """Tenta GPUs disponíveis em ordem até conseguir criar o pod."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{settings.runpod_name_prefix}-{timestamp}-{index:02d}"
    failures: list[str] = []

    for option in gpu_options:
        args = [
            "pod",
            "create",
            f"--template-id={template_id}",
            f"--gpu-id={option.gpu_id}",
            f"--gpu-count={settings.runpod_gpu_count}",
            f"--container-disk-in-gb={settings.runpod_container_disk_gb}",
            f"--cloud-type={settings.runpod_cloud_type}",
            "--volume-mount-path=/workspace",
            f"--name={name}",
            "--env="
            + json.dumps(
                _pod_environment(),
                separators=(",", ":"),
            ),
        ]
        if settings.runpod_network_volume_id:
            # Durante a rodada atual, todos os pods continuam no mesmo volume
            # até que seus pacotes tenham sido integralmente reconciliados.
            args.append(
                f"--network-volume-id={settings.runpod_network_volume_id}"
            )
        else:
            args.append(f"--volume-in-gb={settings.runpod_volume_disk_gb}")
        if settings.runpod_docker_args:
            args.append(f"--docker-args={settings.runpod_docker_args}")
        if settings.runpod_min_cuda_version:
            args.append(
                f"--min-cuda-version={settings.runpod_min_cuda_version}"
            )

        try:
            payload = _runpodctl(*args)
        except RuntimeError as error:
            failures.append(f"{option.gpu_id}: {error}")
            continue

        pod_id = _extract_pod_id(payload)
        try:
            _runpodctl(
                "pod",
                "update",
                pod_id,
                "--env="
                + json.dumps(
                    _pod_environment(pod_id),
                    separators=(",", ":"),
                ),
            )
            details = _wait_for_compute_details(pod_id)
            _validate_compute_balance(details)
        except Exception as error:
            try:
                stop_pod(pod_id)
            except Exception as stop_error:
                failures.append(
                    f"{option.gpu_id}: configuração rejeitada ({error}); "
                    f"falha ao colocar {pod_id} em quarentena: {stop_error}"
                )
                continue
            failures.append(
                f"{option.gpu_id}: configuração rejeitada e pod parado "
                f"({error})"
            )
            continue
        return ManagedPod(
            pod_id=pod_id,
            name=name,
            api_url=(
                f"https://{pod_id}-{settings.runpod_api_port}.proxy.runpod.net"
            ),
            gpu_id=option.gpu_id,
        )

    details = "\n- ".join(failures)
    raise RuntimeError(
        f"Não foi possível criar {name} com nenhuma GPU elegível:\n- {details}"
    )


def _pod_environment(pod_id: str | None = None) -> dict[str, str]:
    """Variáveis gerenciadas para novos pods MinerU.

    O identificador só existe após o create. O update imediato ocorre antes de
    o pod ser registrado como pronto, para que o persistidor use um owner
    estável no volume desde a primeira tarefa aceita pelo cliente.
    """
    environment = {
        "MINERU_API_MAX_CONCURRENT_REQUESTS": "1024",
        "MINERU_LOCAL_WORK_ROOT": "/tmp/mineru-active",
        "MINERU_API_OUTPUT_ROOT": "/tmp/mineru-active/api-output",
        "MINERU_PERSISTENT_RESULTS_ROOT": "/workspace/results",
        "MINERU_MODEL_SOURCE": "local",
        "MINERU_PDF_RENDER_THREADS": "4",
        "MINERU_INTRA_OP_NUM_THREADS": "12",
        "MINERU_INTER_OP_NUM_THREADS": "2",
    }
    if pod_id:
        environment["RUNPOD_POD_ID"] = pod_id
    return environment


def _wait_for_compute_details(
    pod_id: str,
    timeout_seconds: float = 120.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        items = _as_items(_runpodctl("pod", "get", pod_id))
        if items:
            details = items[0]
            if details.get("vcpuCount") and details.get("memoryInGb"):
                return details
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"pod {pod_id} não informou vCPU/RAM em {timeout_seconds:.0f}s"
            )
        time.sleep(2)


def _validate_compute_balance(details: dict[str, object]) -> None:
    vcpu = int(float(str(details.get("vcpuCount") or 0)))
    memory_gb = int(float(str(details.get("memoryInGb") or 0)))
    cost_per_hour = float(str(details.get("costPerHr") or "inf"))

    problems: list[str] = []
    if vcpu < settings.runpod_min_vcpu_count:
        problems.append(
            f"{vcpu} vCPU < mínimo {settings.runpod_min_vcpu_count}"
        )
    if memory_gb < settings.runpod_min_memory_gb:
        problems.append(
            f"{memory_gb} GB RAM < mínimo {settings.runpod_min_memory_gb}"
        )
    if cost_per_hour > settings.runpod_max_cost_per_hour:
        problems.append(
            f"US$ {cost_per_hour:.2f}/h > teto "
            f"US$ {settings.runpod_max_cost_per_hour:.2f}/h"
        )
    if problems:
        raise ValueError("; ".join(problems))


def stop_pod(pod_id: str) -> None:
    _runpodctl("pod", "stop", pod_id)


def start_pod(pod_id: str) -> None:
    _runpodctl("pod", "start", pod_id)


def list_pods() -> tuple[dict[str, object], ...]:
    return tuple(_as_items(_runpodctl("pod", "list", "--all")))


def _health(api_url: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(
            f"{api_url}/health",
            timeout=settings.mineru_health_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


_RUNPOD_PROXY_PATTERN = re.compile(
    r"^https?://(?P<pod_id>[a-z0-9]+)-\d+\.proxy\.runpod\.net(?:/|$)",
    re.IGNORECASE,
)


def pod_from_spec(
    spec: str,
    workers: int | None = None,
) -> ManagedPod:
    """Aceita um ID RunPod ou uma URL MinerU."""
    value = spec.strip().rstrip("/")
    if not value:
        raise ValueError("ID ou URL de pod vazio.")

    if value.lower().startswith(("http://", "https://")):
        match = _RUNPOD_PROXY_PATTERN.match(value)
        pod_id = match.group("pod_id") if match else ""
        return ManagedPod(
            pod_id=pod_id,
            name=f"external-{pod_id or 'url'}",
            api_url=value,
            source="manual",
            workers=workers,
        )

    return ManagedPod(
        pod_id=value,
        name=f"external-{value}",
        api_url=(
            f"https://{value}-{settings.runpod_api_port}.proxy.runpod.net"
        ),
        source="manual",
        workers=workers,
    )


class PodCoordinator:
    """Provisiona, observa e para pods sem bloquear os pods já prontos."""

    def __init__(
        self,
        on_ready: Callable[[ManagedPod, dict[str, Any]], None],
    ) -> None:
        self._on_ready = on_ready
        self._closing = threading.Event()
        self._lock = threading.Lock()
        self._pods: dict[str, ManagedPod] = {}
        self._urls: set[str] = set()
        self._ready_urls: set[str] = set()
        self._threads: list[threading.Thread] = []

    def __enter__(self) -> PodCoordinator:
        self.start_managed()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _start_thread(
        self,
        target: Callable[..., None],
        *args: object,
        name: str,
    ) -> None:
        thread = threading.Thread(
            target=target,
            args=args,
            name=name,
            daemon=True,
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def start_managed(self) -> None:
        reused = self._reconcile_existing()
        if settings.runpod_pod_count == 0:
            reporter.event(
                "RUNPOD_POD_COUNT=0; aguardando pods adicionados.",
                color="yellow",
            )
            return
        missing = max(0, settings.runpod_pod_count - reused)
        if missing == 0:
            reporter.event(
                f"Capacidade inicial satisfeita por {reused} pod(s) "
                "RunPod já em execução.",
                color="green",
            )
            return
        self._start_thread(
            self._prepare_managed,
            missing,
            name="runpod-prepare",
        )

    def _reconcile_existing(self) -> int:
        try:
            observed = list_pods()
        except Exception as error:
            reporter.event(
                "ATENÇÃO: não foi possível reconciliar pods no início: "
                f"{type(error).__name__}: {error}",
                level="WARNING",
                color="yellow",
            )
            return 0

        if settings.runpod_hardware_profile:
            reporter.event(
                "Perfil de hardware ativo; pods históricos sem GPU verificável "
                "não serão reutilizados.",
                color="cyan",
            )
            return 0

        running: list[ManagedPod] = []
        stopped: list[ManagedPod] = []
        for item in observed:
            pod_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            status = str(
                item.get("desiredStatus")
                or item.get("status")
                or "UNKNOWN"
            ).upper()
            if not pod_id or not name.startswith(
                settings.runpod_name_prefix
            ):
                continue
            pod = ManagedPod(
                pod_id=pod_id,
                name=name,
                api_url=(
                    f"https://{pod_id}-{settings.runpod_api_port}"
                    ".proxy.runpod.net"
                ),
                source="reconciled",
                actual_status=status,
            )
            if status == "RUNNING":
                running.append(pod)
            elif status in {"STOPPED", "EXITED"}:
                stopped.append(pod)

        selected = running[: settings.runpod_pod_count]
        missing = settings.runpod_pod_count - len(selected)
        for pod in stopped[: max(0, missing)]:
            reporter.event(
                f"Reiniciando pod gerenciado: {pod.name} | id={pod.pod_id}",
                color="yellow",
            )
            try:
                start_pod(pod.pod_id)
            except Exception as error:
                reporter.event(
                    f"Falha ao iniciar {pod.pod_id}: {error}",
                    level="WARNING",
                    color="yellow",
                )
                continue
            selected.append(
                ManagedPod(
                    pod_id=pod.pod_id,
                    name=pod.name,
                    api_url=pod.api_url,
                    gpu_id=pod.gpu_id,
                    source="restarted",
                    actual_status="RUNNING",
                )
            )
        for pod in selected:
            self._register(pod)
        if len(running) > len(selected):
            reporter.event(
                f"ATENÇÃO: {len(running) - len(selected)} pod(s) BaseIA "
                "adicional(is) já estão RUNNING e não serão alterados.",
                level="WARNING",
                color="yellow",
            )
        reporter.event(
            f"Reconciliação RunPod | encontrados={len(observed)} | "
            f"baseia_ativos={len(running)} | gerenciados={len(selected)}",
            color="cyan",
        )
        return len(selected)

    def _prepare_managed(self, count: int) -> None:
        try:
            if not settings.runpod_template_name:
                raise ValueError(
                    "RUNPOD_TEMPLATE_NAME não foi configurado no .env."
                )
            template_id = resolve_template_id(
                settings.runpod_template_name
            )
            minimum_vram = effective_min_vram_gb()
            gpu_options = available_gpus(minimum_vram)
            selected = ", ".join(
                f"{option.gpu_id} ({option.memory_gb} GB)"
                for option in gpu_options
            )
            reporter.event(
                f"Workload={settings.runpod_workload} | "
                f"VRAM>={minimum_vram} GB | "
                f"vCPU>={settings.runpod_min_vcpu_count} | "
                f"RAM>={settings.runpod_min_memory_gb} GB | "
                f"custo<=US$ {settings.runpod_max_cost_per_hour:.2f}/h",
                color="cyan",
            )
            reporter.event(
                f"GPUs elegíveis por disponibilidade: {selected}",
                color="cyan",
            )
        except Exception as error:
            reporter.event(
                "ATENÇÃO: provisionamento automático indisponível: "
                f"{type(error).__name__}: {error}. "
                "Aguardando pods adicionados manualmente.",
                level="WARNING",
                color="yellow",
            )
            return

        for index in range(1, count + 1):
            if self._closing.is_set():
                return
            self._start_thread(
                self._provision,
                template_id,
                index,
                gpu_options,
                name=f"runpod-create-{index}",
            )

    def _provision(
        self,
        template_id: str,
        index: int,
        gpu_options: tuple[GpuOption, ...],
    ) -> None:
        try:
            pod = create_pod(
                template_id=template_id,
                index=index,
                gpu_options=gpu_options,
            )
        except Exception as error:
            reporter.event(
                "ATENÇÃO: falha ao criar pod "
                f"{index}: {type(error).__name__}: {error}",
                level="ERROR",
                color="red",
            )
            return

        if self._closing.is_set():
            try:
                stop_pod(pod.pod_id)
            except Exception as error:
                reporter.event(
                    f"ATENÇÃO: falha ao parar {pod.pod_id}: {error}",
                    level="WARNING",
                    color="yellow",
                )
            return

        reporter.event(
            f"Pod criado: {pod.name} | id={pod.pod_id} | gpu={pod.gpu_id}",
            color="cyan",
        )
        self._register(pod)

    def add_pod_spec(
        self,
        spec: str,
        workers: int | None = None,
    ) -> bool:
        pod = pod_from_spec(spec, workers)
        if pod.pod_id:
            observed = {
                str(item.get("id")): item
                for item in list_pods()
                if item.get("id")
            }.get(pod.pod_id)
            status = str(
                (observed or {}).get("desiredStatus")
                or (observed or {}).get("status")
                or "UNKNOWN"
            ).upper()
            if observed is not None:
                pod = ManagedPod(
                    pod_id=pod.pod_id,
                    name=str(observed.get("name") or pod.name),
                    api_url=pod.api_url,
                    source="manual",
                    actual_status=status,
                    workers=pod.workers,
                )
            if status not in {"RUNNING", "UNKNOWN"}:
                reporter.event(
                    f"Iniciando pod parado: {pod.pod_id} | estado={status}",
                    color="yellow",
                )
                start_pod(pod.pod_id)
                pod = ManagedPod(
                    pod_id=pod.pod_id,
                    name=pod.name,
                    api_url=pod.api_url,
                    source=pod.source,
                    actual_status="RUNNING",
                    workers=pod.workers,
                )
        added = self._register(pod)
        if added:
            reporter.event(
                f"Pod adicionado: {pod.pod_id or pod.api_url}",
                color="cyan",
            )
        return added

    def _register(self, pod: ManagedPod) -> bool:
        with self._lock:
            if self._closing.is_set() or pod.api_url in self._urls:
                return False
            self._urls.add(pod.api_url)
            if pod.pod_id:
                self._pods[pod.pod_id] = pod

        self._start_thread(
            self._watch_ready,
            pod,
            name=f"runpod-ready-{pod.pod_id or len(self._urls)}",
        )
        return True

    def _watch_ready(self, pod: ManagedPod) -> None:
        deadline = time.monotonic() + settings.runpod_startup_timeout_seconds
        while not self._closing.is_set():
            health = _health(pod.api_url)
            if health is not None:
                if pod.workers is not None:
                    health = {
                        **health,
                        "_client_capacity_override": pod.workers,
                    }
                with self._lock:
                    if pod.api_url in self._ready_urls:
                        return
                    self._ready_urls.add(pod.api_url)
                reporter.event(
                    f"Pod pronto: {pod.name} | {pod.api_url}",
                    color="green",
                )
                self._on_ready(pod, health)
                return
            if time.monotonic() >= deadline:
                reporter.event(
                    f"ATENÇÃO: timeout aguardando {pod.name}; "
                    "a extração continuará com os demais pods.",
                    level="WARNING",
                    color="yellow",
                )
                if pod.pod_id:
                    self.quarantine_defective(
                        pod.pod_id,
                        "timeout de inicialização",
                    )
                return
            self._closing.wait(settings.runpod_startup_poll_seconds)

    def quarantine_defective(self, pod_id: str, reason: str) -> None:
        with self._lock:
            pod = self._pods.pop(pod_id, None)
            if pod is None:
                return
            self._ready_urls.discard(pod.api_url)
        try:
            stop_pod(pod_id)
            reporter.event(
                f"Pod defeituoso parado e preservado: {pod.name} | "
                f"id={pod_id} | motivo={reason}",
                level="ERROR",
                color="red",
            )
        except Exception as error:
            reporter.event(
                f"Falha ao parar pod defeituoso {pod_id}: {error}",
                level="ERROR",
                color="red",
            )
            return
        if (
            not self._closing.is_set()
            and settings.runpod_pod_count > 0
        ):
            self._start_thread(
                self._prepare_managed,
                1,
                name=f"runpod-replace-{pod_id}",
            )

    def close(self) -> None:
        self._closing.set()
        with self._lock:
            threads = tuple(self._threads)
        for thread in threads:
            thread.join(
                timeout=settings.mineru_health_timeout_seconds + 2,
            )

        with self._lock:
            pods = tuple(self._pods.values())
        failures: list[str] = []
        for pod in reversed(pods):
            try:
                stop_pod(pod.pod_id)
                reporter.event(
                    f"Pod parado: {pod.name} | id={pod.pod_id}",
                    color="cyan",
                )
            except Exception as error:
                failures.append(
                    f"{pod.pod_id}: {type(error).__name__}: {error}"
                )
        if failures:
            reporter.event(
                "ATENÇÃO: falha ao parar pods:\n- " + "\n- ".join(failures),
                level="WARNING",
                color="yellow",
            )

@contextmanager
def managed_mineru_pods(
    on_ready: Callable[[ManagedPod, dict[str, Any]], None],
) -> Iterator[PodCoordinator]:
    """Provisiona pods e garante apenas seu stop ao final."""
    with PodCoordinator(on_ready) as coordinator:
        yield coordinator
