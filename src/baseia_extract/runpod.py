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
from typing import Iterator

from .settings import settings


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


def create_pod(*, template_id: str, index: int) -> ManagedPod:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{settings.runpod_name_prefix}-{timestamp}-{index:02d}"
    payload = _runpodctl(
        "pod",
        "create",
        f"--template-id={template_id}",
        f"--gpu-id={settings.runpod_gpu_id}",
        f"--gpu-count={settings.runpod_gpu_count}",
        f"--terminate-after={settings.runpod_terminate_after}",
        f"--name={name}",
    )
    pod_id = _extract_pod_id(payload)
    return ManagedPod(
        pod_id=pod_id,
        name=name,
        api_url=f"https://{pod_id}-{settings.runpod_api_port}.proxy.runpod.net",
    )


def delete_pod(pod_id: str) -> None:
    _runpodctl("pod", "delete", pod_id)


def _healthy(api_url: str) -> bool:
    request = urllib.request.Request(
        f"{api_url}/health",
        headers={"Accept": "application/json", "User-Agent": "BaseIA-Extract/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.mineru_health_timeout_seconds,
        ) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def wait_until_ready(pods: tuple[ManagedPod, ...]) -> None:
    deadline = time.monotonic() + settings.runpod_startup_timeout_seconds
    pending = {pod.pod_id: pod for pod in pods}

    while pending:
        for pod_id, pod in tuple(pending.items()):
            if _healthy(pod.api_url):
                print(f"Pod pronto: {pod.name} | {pod.api_url}")
                pending.pop(pod_id)
        if not pending:
            return
        if time.monotonic() >= deadline:
            names = ", ".join(pod.name for pod in pending.values())
            raise TimeoutError(f"Pods não ficaram prontos dentro do limite: {names}")
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
