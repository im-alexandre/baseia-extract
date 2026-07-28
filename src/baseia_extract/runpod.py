from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from .settings import settings


REQUIRED_MINERU_ROUTES = frozenset(
    {
        "/health",
        "/file_parse",
        "/tasks",
        "/tasks/{task_id}",
        "/tasks/{task_id}/result",
    }
)


class UnexpectedPodServiceError(RuntimeError):
    """O proxy respondeu, mas o processo exposto não é a API esperada."""


@dataclass(frozen=True, slots=True)
class ManagedPod:
    pod_id: str
    name: str
    api_url: str


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
        for key in ("items", "templates", "pods", "data"):
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


def _runtime_environment() -> dict[str, str]:
    """Configuração que precisa ser idêntica no cliente e na API remota."""
    return {
        "MINERU_VERSION": settings.mineru_version,
        "MINERU_VENV": settings.mineru_remote_venv,
        "MINERU_MODELS_ROOT": settings.mineru_remote_models_root,
        "MINERU_API_OUTPUT_ROOT": settings.mineru_remote_output_root,
        "MINERU_API_MAX_CONCURRENT_REQUESTS": str(
            settings.mineru_workers_per_pod
        ),
        "MINERU_API_TASK_RETENTION_SECONDS": str(
            settings.mineru_api_task_retention_seconds
        ),
        "MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS": str(
            settings.mineru_api_task_cleanup_interval_seconds
        ),
        "MINERU_API_ENABLE_FASTAPI_DOCS": "true",
        "MINERU_PREPARE_TIMEOUT_SECONDS": str(
            int(settings.runpod_startup_timeout_seconds)
        ),
        "PORT": str(settings.runpod_api_port),
    }


def create_pod(*, template_id: str, index: int) -> ManagedPod:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{settings.runpod_name_prefix}-{timestamp}-{index:02d}"
    create_args = [
        "pod",
        "create",
        f"--template-id={template_id}",
        f"--gpu-id={settings.runpod_gpu_id}",
        f"--gpu-count={settings.runpod_gpu_count}",
        f"--ports={settings.runpod_api_port}/http",
        f"--terminate-after={settings.runpod_terminate_after}",
        f"--name={name}",
        "--env",
        json.dumps(
            _runtime_environment(),
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    ]
    if settings.network_volume_id:
        create_args.append(f"--network-volume-id={settings.network_volume_id}")

    payload = _runpodctl(*create_args)
    pod_id = _extract_pod_id(payload)
    return ManagedPod(
        pod_id=pod_id,
        name=name,
        api_url=f"https://{pod_id}-{settings.runpod_api_port}.proxy.runpod.net",
    )


def delete_pod(pod_id: str) -> None:
    _runpodctl("pod", "delete", pod_id)


def _read_json_endpoint(api_url: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_url}{path}",
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-Extract/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=settings.mineru_health_timeout_seconds,
    ) as response:
        payload = response.read().decode("utf-8")

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise TypeError(f"{path} não contém um objeto JSON.")
    return data


def _pending_probe_status(
    api_url: str,
    path: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        return True, "ok", _read_json_endpoint(api_url, path)
    except urllib.error.HTTPError as error:
        return False, f"{path} respondeu HTTP {error.code}", None
    except urllib.error.URLError as error:
        return False, f"proxy indisponível: {error.reason}", None
    except TimeoutError:
        return False, f"timeout consultando {path}", None
    except json.JSONDecodeError:
        return False, f"{path} ainda não retornou JSON válido", None
    except (OSError, TypeError) as error:
        return False, f"{path} indisponível: {error}", None


def _require_health_integer(
    *,
    api_url: str,
    health: dict[str, Any],
    key: str,
    expected: int,
) -> int:
    observed = health.get(key)
    try:
        parsed = int(observed)
    except (TypeError, ValueError) as error:
        raise UnexpectedPodServiceError(
            f"/health de {api_url} não informou {key} corretamente: "
            f"{observed!r}."
        ) from error

    if parsed != expected:
        raise UnexpectedPodServiceError(
            f"Configuração divergente em {api_url}: "
            f"{key}={parsed}, esperado={expected}."
        )
    return parsed


def _probe_mineru_api(api_url: str) -> tuple[bool, str]:
    """Valida rotas, versão, saúde interna e configuração do MinerU."""
    available, status, openapi = _pending_probe_status(api_url, "/openapi.json")
    if not available or openapi is None:
        return False, status

    raw_paths = openapi.get("paths")
    if not isinstance(raw_paths, dict):
        raise UnexpectedPodServiceError(
            f"{api_url} respondeu a /openapi.json sem um mapa de rotas válido."
        )

    observed_routes = {str(path) for path in raw_paths}
    missing_routes = REQUIRED_MINERU_ROUTES - observed_routes
    if missing_routes:
        service_hint = (
            " O serviço parece ser o servidor OpenAI do vLLM."
            if any(route.startswith("/v1/") for route in observed_routes)
            else ""
        )
        observed_preview = ", ".join(sorted(observed_routes)[:20])
        raise UnexpectedPodServiceError(
            f"{api_url} está respondendo, mas não é a API MinerU esperada."
            f"{service_hint} Rotas ausentes: {sorted(missing_routes)}. "
            f"Rotas observadas: {observed_preview}. Verifique a imagem e remova "
            "Docker Entrypoint que sobrescreva o entrypoint da imagem no "
            "template RunPod."
        )

    available, status, health = _pending_probe_status(api_url, "/health")
    if not available or health is None:
        return False, status

    health_status = str(health.get("status", "")).lower()
    if health_status != "healthy":
        return False, f"MinerU ainda não está saudável: {health}"

    observed_version = str(health.get("version", "")).strip()
    if observed_version != settings.mineru_version:
        raise UnexpectedPodServiceError(
            f"Versão MinerU divergente em {api_url}: "
            f"servidor={observed_version!r}, esperada={settings.mineru_version!r}."
        )

    concurrency = _require_health_integer(
        api_url=api_url,
        health=health,
        key="max_concurrent_requests",
        expected=settings.mineru_workers_per_pod,
    )
    retention = _require_health_integer(
        api_url=api_url,
        health=health,
        key="task_retention_seconds",
        expected=settings.mineru_api_task_retention_seconds,
    )
    cleanup_interval = _require_health_integer(
        api_url=api_url,
        health=health,
        key="task_cleanup_interval_seconds",
        expected=settings.mineru_api_task_cleanup_interval_seconds,
    )

    return (
        True,
        (
            f"MinerU {observed_version}; concorrência={concurrency}; "
            f"retenção={retention}s; limpeza={cleanup_interval}s"
        ),
    )


def wait_until_ready(pods: tuple[ManagedPod, ...]) -> None:
    deadline = time.monotonic() + settings.runpod_startup_timeout_seconds
    pending = {pod.pod_id: pod for pod in pods}
    last_status: dict[str, str] = {}

    while pending:
        for pod_id, pod in tuple(pending.items()):
            ready, status = _probe_mineru_api(pod.api_url)
            last_status[pod_id] = status
            if ready:
                print(f"Pod MinerU pronto: {pod.name} | {pod.api_url} | {status}")
                pending.pop(pod_id)

        if not pending:
            return

        if time.monotonic() >= deadline:
            details = "\n".join(
                f"- {pod.name} ({pod.api_url}): "
                f"{last_status.get(pod_id, 'sem resposta')}"
                for pod_id, pod in pending.items()
            )
            raise TimeoutError(
                "Pods não expuseram o contrato MinerU dentro do limite:\n"
                f"{details}"
            )

        time.sleep(settings.runpod_startup_poll_seconds)


@contextmanager
def managed_mineru_pods() -> Iterator[tuple[ManagedPod, ...]]:
    """Cria pods temporários e garante sua exclusão ao final da extração."""
    if not settings.runpod_template_name:
        raise ValueError("RUNPOD_TEMPLATE_NAME não foi configurado no .env.")

    template_id = resolve_template_id(settings.runpod_template_name)
    created: list[ManagedPod] = []
    try:
        for index in range(1, settings.runpod_pod_count + 1):
            pod = create_pod(template_id=template_id, index=index)
            created.append(pod)
            print(f"Pod criado: {pod.name} | id={pod.pod_id}")

        pods = tuple(created)
        wait_until_ready(pods)
        yield pods
    finally:
        failures: list[str] = []
        for pod in reversed(created):
            try:
                delete_pod(pod.pod_id)
                print(f"Pod encerrado: {pod.name} | id={pod.pod_id}")
            except Exception as error:
                failures.append(f"{pod.pod_id}: {type(error).__name__}: {error}")
        if failures:
            print("ATENÇÃO: falha ao encerrar pods:\n- " + "\n- ".join(failures))
