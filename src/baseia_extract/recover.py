from __future__ import annotations

import json
import os
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import httpx
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_exponential

from .extract_control import normalize_api_urls
from .layout import document_layout
from .mineru import _completed, _extract_result_zip
from .schemas import ExtractionManifest
from .settings import settings


class RecoveryRecord(BaseModel):
    sha256: str
    document_id: str
    pod_id: str
    task_id: str
    completed_at: datetime | None = None
    zip_path: Path | None = None
    recovered_at: datetime | None = None
    applied_at: datetime | None = None
    error: str | None = None


def _retryable(error: BaseException) -> bool:
    if isinstance(error, httpx.TimeoutException | httpx.NetworkError):
        return True
    return (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code >= 500
    )


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_retryable),
        reraise=True,
    ):
        with attempt:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
    raise RuntimeError("Retry HTTP encerrado sem resposta.")


def _atomic_record(path: Path, record: RecoveryRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            record.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _known_tasks(api_urls: tuple[str, ...]) -> list[dict[str, str]]:
    selected_urls = {url.rstrip("/") for url in api_urls}
    records: list[dict[str, str]] = []
    for path in settings.document_store_dir.rglob("manifest.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == 2
        ):
            stage_runs = payload.get("stage_runs")
            for state in (
                stage_runs if isinstance(stage_runs, list) else []
            ):
                if not isinstance(state, dict) or state.get("stage") != "extract":
                    continue
                api_url = str(state.get("api_url") or "").rstrip("/")
                task_id = str(state.get("task_id") or "")
                if api_url not in selected_urls or not task_id:
                    continue
                records.append(
                    {
                        "task_id": task_id,
                        "pod_id": str(state.get("pod_id") or ""),
                        "api_url": api_url,
                        "sha256": str(payload.get("sha256") or ""),
                        "document_id": str(
                            payload.get("document_id") or ""
                        ),
                        "filename": str(payload.get("filename") or ""),
                    }
                )
            continue
        try:
            manifest = ExtractionManifest.model_validate(payload)
        except ValueError:
            continue
        api_url = (manifest.api_url or "").rstrip("/")
        if api_url not in selected_urls or not manifest.task_id:
            continue
        records.append(
            {
                "task_id": manifest.task_id,
                "pod_id": manifest.pod_id or "",
                "api_url": api_url,
                "sha256": manifest.sha256,
                "document_id": manifest.document_id,
                "filename": manifest.filename,
            }
        )
    return records


def _has_middle_json(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            return any(
                not member.is_dir()
                and member.filename.casefold().endswith("_middle.json")
                for member in archive.infolist()
            )
    except (OSError, zipfile.BadZipFile):
        return False


async def _recover(
    api_urls: tuple[str, ...],
    *,
    downloads: int,
    apply: bool,
) -> dict[str, int]:
    tasks = _known_tasks(api_urls)
    recovery_root = settings.data_dir / "mineru_recovery"
    raw_root = recovery_root / "raw"
    records_root = recovery_root / "records"
    status_limiter = anyio.CapacityLimiter(
        min(64, max(8, len(api_urls) * 12))
    )
    download_limiter = anyio.CapacityLimiter(max(1, downloads))
    limits = httpx.Limits(
        max_connections=max(16, len(api_urls) * 8),
        max_keepalive_connections=max(8, len(api_urls) * 4),
        keepalive_expiry=60,
    )
    timeout = httpx.Timeout(
        connect=30,
        read=settings.mineru_result_timeout_seconds,
        write=300,
        pool=30,
    )
    clients = {
        api_url: httpx.AsyncClient(
            base_url=api_url,
            limits=limits,
            timeout=timeout,
        )
        for api_url in api_urls
    }
    completed: dict[str, tuple[dict[str, str], dict[str, Any]]] = {}
    counts = {
        "known_task_ids": len(tasks),
        "available_completed_tasks": 0,
        "unique_completed_documents": 0,
        "already_persisted": 0,
        "downloaded": 0,
        "already_downloaded": 0,
        "download_errors": 0,
        "applied": 0,
        "not_found": 0,
        "processing": 0,
        "status_errors": 0,
    }

    async def inspect_task(task: dict[str, str]) -> None:
        async with status_limiter:
            try:
                response = await _request(
                    clients[task["api_url"]],
                    "GET",
                    f"/tasks/{task['task_id']}",
                )
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    counts["not_found"] += 1
                else:
                    counts["status_errors"] += 1
                return
            except Exception:
                counts["status_errors"] += 1
                return

        payload = response.json()
        status = str(payload.get("status", "unknown"))
        if status != "completed":
            if status in {"processing", "queued"}:
                counts["processing"] += 1
            return
        counts["available_completed_tasks"] += 1
        current = completed.get(task["sha256"])
        completed_at = str(payload.get("completed_at") or "")
        current_at = str(current[1].get("completed_at") or "") if current else ""
        if current is None or completed_at > current_at:
            completed[task["sha256"]] = (task, payload)

    try:
        async with anyio.create_task_group() as group:
            for task in tasks:
                group.start_soon(inspect_task, task)

        counts["unique_completed_documents"] = len(completed)
        print(
            "Varredura concluída: "
            f"{counts['available_completed_tasks']} tarefas prontas, "
            f"{len(completed)} documentos únicos.",
            flush=True,
        )

        async def download_result(
            task: dict[str, str],
            payload: dict[str, Any],
        ) -> None:
            output_dir = (
                document_layout(task).mineru_dir
            )
            if _completed(output_dir):
                counts["already_persisted"] += 1
                return

            task_dir = raw_root / task["sha256"][:2] / task["sha256"]
            zip_path = task_dir / f"{task['task_id']}.zip"
            record_path = records_root / f"{task['sha256']}.json"
            record = RecoveryRecord(
                sha256=task["sha256"],
                document_id=task["document_id"],
                pod_id=task["pod_id"],
                task_id=task["task_id"],
                completed_at=payload.get("completed_at"),
                zip_path=zip_path,
            )
            if zip_path.exists() and _has_middle_json(zip_path):
                counts["already_downloaded"] += 1
            else:
                task_dir.mkdir(parents=True, exist_ok=True)
                handle, temporary_name = tempfile.mkstemp(
                    prefix=f".{task['task_id']}.",
                    suffix=".zip",
                    dir=task_dir,
                )
                os.close(handle)
                temporary = Path(temporary_name)
                try:
                    async with download_limiter:
                        async for attempt in AsyncRetrying(
                            stop=stop_after_attempt(3),
                            wait=wait_exponential(
                                multiplier=2,
                                min=2,
                                max=30,
                            ),
                            retry=retry_if_exception(_retryable),
                            reraise=True,
                        ):
                            with attempt:
                                async with clients[task["api_url"]].stream(
                                    "GET",
                                    f"/tasks/{task['task_id']}/result",
                                ) as response:
                                    response.raise_for_status()
                                    with temporary.open("wb") as destination:
                                        async for chunk in response.aiter_bytes(
                                            1024 * 1024
                                        ):
                                            destination.write(chunk)
                    if not _has_middle_json(temporary):
                        raise ValueError(
                            "ZIP recuperado sem middle JSON válido."
                        )
                    os.replace(temporary, zip_path)
                    counts["downloaded"] += 1
                    record.recovered_at = datetime.now(timezone.utc)
                    print(
                        "Recuperados "
                        f"{counts['downloaded'] + counts['already_downloaded']}"
                        f"/{len(completed) - counts['already_persisted']}",
                        flush=True,
                    )
                except Exception as error:
                    counts["download_errors"] += 1
                    record.error = f"{type(error).__name__}: {error}"
                finally:
                    temporary.unlink(missing_ok=True)

            if (
                apply
                and record.error is None
                and zip_path.exists()
                and not _completed(output_dir)
            ):
                try:
                    await anyio.to_thread.run_sync(
                        _extract_result_zip,
                        zip_path,
                        output_dir,
                    )
                    record.applied_at = datetime.now(timezone.utc)
                    counts["applied"] += 1
                except Exception as error:
                    record.error = f"{type(error).__name__}: {error}"
                    counts["download_errors"] += 1
            _atomic_record(record_path, record)

        async with anyio.create_task_group() as group:
            for task, payload in completed.values():
                group.start_soon(download_result, task, payload)
    finally:
        async with anyio.create_task_group() as group:
            for client in clients.values():
                group.start_soon(client.aclose)

    print(RecoveryRecord.__name__, counts, flush=True)
    return counts


def recover(
    api_urls: Iterable[str],
    downloads: int = 4,
    apply: bool = False,
) -> dict[str, int]:
    """Recupera resultados já concluídos sem reenviar documentos."""
    normalized = normalize_api_urls(
        tuple(
            str(api_url).strip().rstrip("/")
            for api_url in api_urls
            if api_url
        )
    )
    if not normalized:
        raise ValueError("Informe pelo menos uma URL de serviço MinerU.")
    return anyio.run(
        partial(
            _recover,
            normalized,
            downloads=downloads,
            apply=apply,
        )
    )
