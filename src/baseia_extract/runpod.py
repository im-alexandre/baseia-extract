from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from .settings import settings


@dataclass(frozen=True, slots=True)
class RunPodInstance:
    pod_id: str
    name: str
    api_url: str


def _runpodctl() -> str:
    executable = shutil.which("runpodctl")
    if executable is None:
        raise FileNotFoundError("runpodctl não foi encontrado no PATH.")
    return executable


def _run(*args: str) -> str:
    result = subprocess.run(
        [_runpodctl(), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = "\n".join(
        part for part in (result.stdout.strip(), result.stderr.strip()) if part
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"runpodctl {' '.join(args)} falhou com código {result.returncode}:\n{output}"
        )
    return output


def _json(output: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Saída JSON inválida do runpodctl:\n{output}") from error


def resolve_template_id(template_name: str) -> str:
    """Resolve um template privado pelo nome exato."""
    payload = _json(_run("template", "list", "--type", "user", "--limit", "100"))
    templates = payload if isinstance(payload, list) else payload.get("templates", [])
    matches = [
        item
        for item in templates
        if isinstance(item, dict)
        and str(item.get("name", "")).strip().casefold() == template_name.strip().casefold()
    ]
    if not matches:
        raise ValueError(f"Template RunPod não encontrado: {template_name!r}.")
    if len(matches) > 1:
        ids = [str(item.get("id")) for item in matches]
        raise ValueError(
            f"Há mais de um template RunPod chamado {template_name!r}: {ids}."
        )
    template_id = str(matches[0].get("id", "")).strip()
    if not template_id:
        raise RuntimeError(f"Template {template_name!r} não possui ID válido.")
    return template_id


def _extract_pod_id(output: str) -> str:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = None

    def find_id(value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("id", "podId", "pod_id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for child in value.values():
                candidate = find_id(child)
                if candidate:
                    return candidate
        elif isinstance(value, list):
            for child in value:
                candidate = find_id(child)
                if candidate:
                    return candidate
        return None

    if payload is not None:
        candidate = find_id(payload)
        if candidate:
            return candidate

    for pattern in (
        r"(?i)pod(?:\s+id|_id|Id)?\s*[:=]\s*[\"']?([a-z0-9-]{6,})",
        r"https://([a-z0-9-]+)-\d+\.proxy\.runpod\.net",
    ):
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    raise RuntimeError(f"Não foi possível identificar o pod criado:\n{output}")


def create_pod(template_id: str, index: int) -> RunPodInstance:
    name = f"{settings.runpod_name_prefix}-{index:02d}"
    output = _run(
        "pod",
        "create",
        "--template-id",
        template_id,
        "--gpu-id",
        settings.runpod_gpu_id,
        "--gpu-count",
        str(settings.runpod_gpu_count),
        "--name",
        name,
    )
    pod_id = _extract_pod_id(output)
    return RunPodInstance(
        pod_id=pod_id,
        name=name,
        api_url=f"https://{pod_id}-{settings.runpod_api_port}.proxy.runpod.net",
    )


def delete_pod(pod_id: str) -> None:
    """Termina o pod, liberando GPU e armazenamento efêmero."""
    _run("pod", "delete", pod_id)


def _wait_until_ready(pod: RunPodInstance, healthcheck: Any) -> None:
    deadline = time.monotonic() + settings.runpod_startup_timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            healthcheck(pod.api_url)
            return
        except Exception as error:
            last_error = error
            time.sleep(settings.runpod_startup_poll_seconds)
    raise TimeoutError(
        f"Pod {pod.pod_id} não ficou pronto em "
        f"{settings.runpod_startup_timeout_seconds:.0f}s: {last_error}"
    )


@contextmanager
def managed_mineru_pods(healthcheck: Any) -> Iterator[tuple[RunPodInstance, ...]]:
    """Cria, aguarda e sempre termina os pods usados por uma tarefa MinerU."""
    template_id = resolve_template_id(settings.runpod_template_name)
    pods: list[RunPodInstance] = []
    try:
        for index in range(1, settings.runpod_pod_count + 1):
            pod = create_pod(template_id, index)
            pods.append(pod)
            print(f"Pod criado: {pod.name} ({pod.pod_id})")
        for pod in pods:
            _wait_until_ready(pod, healthcheck)
            print(f"Pod pronto: {pod.api_url}")
        yield tuple(pods)
    finally:
        failures: list[str] = []
        for pod in reversed(pods):
            try:
                delete_pod(pod.pod_id)
                print(f"Pod terminado: {pod.name} ({pod.pod_id})")
            except Exception as error:
                failures.append(f"{pod.pod_id}: {type(error).__name__}: {error}")
        if failures:
            print("ATENÇÃO: falha ao terminar pods:\n- " + "\n- ".join(failures))
