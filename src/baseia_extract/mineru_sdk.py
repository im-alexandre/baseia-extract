from __future__ import annotations

# ruff: noqa: I001

import os

# MinerU reads this setting from the process environment. Keep it before every
# MinerU import so GET /health remains the binding concurrency limit.
os.environ["MINERU_API_MAX_CONCURRENT_REQUESTS"] = "1024"

import asyncio
import hashlib
import shutil
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from mineru.cli.api_protocol import (
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_PROCESSING_WINDOW_SIZE,
)
from mineru.cli.client import (
    InputDocument,
    PlannedTask,
    ServerHealth,
    TaskFailure,
    build_http_timeout,
    build_request_form_data,
    build_task_execution_progress,
    execute_planned_tasks,
    fetch_server_health,
    normalize_base_url,
    plan_tasks,
    resolve_effective_max_concurrent_requests,
    resolve_submit_concurrency,
    run_planned_task,
)
from mineru.utils.config_reader import (
    get_max_concurrent_requests,
)
from mineru.version import __version__ as mineru_version

from .mineru import (
    ManifestStore,
    WorkItem,
    _completed,
    _load_manifest,
    _write_frame_atomic,
    _write_json_atomic,
)
from .reporting import reporter
from .settings import settings


CLIENT_CONCURRENCY_CAP = 1024


class ExtractionStopped(RuntimeError):
    """Raised internally when a graceful stop prevents a new submission."""


def _document_stem(item: WorkItem) -> str:
    document_id = item.document.document_id.strip()
    if not document_id:
        raise ValueError("Documento sem document_id.")
    if all(
        character.isascii() and (character.isalnum() or character in "._-")
        for character in document_id
    ):
        return document_id
    return "baseia-" + hashlib.sha256(document_id.encode("utf-8")).hexdigest()


def _input_documents(
    entries: list[tuple[WorkItem, str]],
) -> list[InputDocument]:
    documents: list[InputDocument] = []
    seen_stems: set[str] = set()
    for item, stem in entries:
        normalized_stem = stem.casefold()
        if normalized_stem in seen_stems:
            raise ValueError(
                f"O inventário produziu identificadores MinerU duplicados: {stem}"
            )
        seen_stems.add(normalized_stem)
        path = item.document.path
        if not path.is_file():
            raise FileNotFoundError(path)
        documents.append(
            InputDocument(
                path=path,
                suffix=".pdf",
                stem=stem,
                effective_pages=max(item.document.page_count or 1, 1),
                order=item.position,
            )
        )
    return documents


def _volume_groups(
    entries: list[tuple[WorkItem, str]],
) -> list[list[tuple[WorkItem, str]]]:
    groups: dict[str, list[tuple[WorkItem, str]]] = defaultdict(list)
    for item, stem in entries:
        resolved = item.output_dir.resolve()
        volume = (resolved.drive or resolved.anchor).casefold()
        groups[volume].append((item, stem))
    return list(groups.values())


def _remove_returned_source(root: Path, stem: str) -> None:
    prefix = f"{stem}_origin.".casefold()
    for path in root.rglob("*"):
        if path.is_file() and path.name.casefold().startswith(prefix):
            path.unlink()


def _replace_directory(candidate: Path, destination: Path) -> None:
    if destination.exists() and not destination.is_dir():
        raise NotADirectoryError(destination)
    backup = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.previous")
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(candidate, destination)
    except BaseException:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)


def _install_document_result(
    staging_root: Path,
    item: WorkItem,
    stem: str,
) -> bool:
    staged_document = staging_root / stem
    if not staged_document.is_dir() or not _completed(staged_document):
        return False

    _remove_returned_source(staged_document, stem)
    destination = item.output_dir
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.sdk.",
            dir=destination.parent,
        )
    )
    try:
        os.replace(staged_document, candidate / stem)
        if not _completed(candidate):
            raise ValueError(
                f"Resultado MinerU incompleto para {item.document.document_id}."
            )
        _replace_directory(candidate, destination)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
    return True


async def _run_group(
    *,
    http_client: httpx.AsyncClient,
    server_health: ServerHealth,
    entries: list[tuple[WorkItem, str]],
    effective_max_concurrent_requests: int,
    stop_event: threading.Event,
) -> tuple[set[str], list[TaskFailure], int, int]:
    first_item = entries[0][0]
    staging_parent = first_item.output_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    documents = _input_documents(entries)
    planned_tasks = plan_tasks(
        documents=documents,
        backend=settings.mineru_backend,
        processing_window_size=(
            server_health.processing_window_size
            if settings.mineru_backend == "pipeline"
            else DEFAULT_PROCESSING_WINDOW_SIZE
        ),
    )
    concurrency = resolve_submit_concurrency(
        effective_max_concurrent_requests,
        len(planned_tasks),
    )
    progress = build_task_execution_progress(planned_tasks)
    form_data = build_request_form_data(
        lang="ch",
        backend=settings.mineru_backend,
        method="auto",
        formula_enable=True,
        table_enable=True,
        image_analysis=True,
        server_url=None,
        start_page_id=0,
        end_page_id=None,
        client_side_output_generation=False,
    )

    with tempfile.TemporaryDirectory(
        prefix=".mineru-sdk-",
        dir=staging_parent,
    ) as temporary:
        staging_root = Path(temporary)

        async def run_task(planned_task: PlannedTask) -> None:
            if stop_event.is_set():
                raise ExtractionStopped("Execução interrompida antes da submissão.")
            await run_planned_task(
                client=http_client,
                server_health=server_health,
                planned_task=planned_task,
                progress=progress,
                backend=settings.mineru_backend,
                parse_method="auto",
                visualization_context=None,
                form_data=form_data,
                output_dir=staging_root,
                live_renderer=None,
                client_side_output_generation=False,
            )

        failures = await execute_planned_tasks(
            planned_tasks=planned_tasks,
            concurrency=concurrency,
            task_runner=run_task,
        )
        installed: set[str] = set()
        for item, stem in entries:
            try:
                if _install_document_result(staging_root, item, stem):
                    installed.add(stem)
            except (OSError, ValueError) as error:
                failures.append(
                    TaskFailure(
                        task_index=item.position + 1,
                        document_stems=(stem,),
                        message=(
                            "Falha ao instalar o ZIP MinerU: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                )
        return installed, failures, len(planned_tasks), concurrency


async def _orchestrate(
    *,
    api_url: str,
    entries: list[tuple[WorkItem, str]],
    stop_event: threading.Event,
) -> dict[str, Any]:
    timeout = build_http_timeout()
    all_installed: set[str] = set()
    all_failures: list[TaskFailure] = []
    planned_task_count = 0
    peak_concurrency = 0

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        server_health = await fetch_server_health(
            http_client,
            normalize_base_url(api_url),
        )
        local_max = get_max_concurrent_requests(default=DEFAULT_MAX_CONCURRENT_REQUESTS)
        effective_max = resolve_effective_max_concurrent_requests(
            local_max=local_max,
            server_max=server_health.max_concurrent_requests,
        )
        reporter.event(
            "Orquestrador MinerU oficial | "
            f"cliente={local_max} | "
            f"api={server_health.max_concurrent_requests} | "
            f"efetiva={effective_max} | "
            f"janela={server_health.processing_window_size}",
            color="cyan",
        )

        for group in _volume_groups(entries):
            installed, failures, task_count, concurrency = await _run_group(
                http_client=http_client,
                server_health=server_health,
                entries=group,
                effective_max_concurrent_requests=effective_max,
                stop_event=stop_event,
            )
            all_installed.update(installed)
            all_failures.extend(failures)
            planned_task_count += task_count
            peak_concurrency = max(peak_concurrency, concurrency)

    return {
        "installed": all_installed,
        "failures": all_failures,
        "server_max_concurrent_requests": (server_health.max_concurrent_requests),
        "processing_window_size": server_health.processing_window_size,
        "effective_max_concurrent_requests": effective_max,
        "planned_task_count": planned_task_count,
        "peak_concurrency": peak_concurrency,
    }


def pending_count(path: Path) -> int:
    manifests = ManifestStore()
    return sum(
        settings.mineru_overwrite
        or not _completed(item.output_dir)
        or manifests.load(item).status != "ok"
        for item in _load_manifest(path)
    )


def _result_row(
    item: WorkItem,
    *,
    status: str,
    api_url: str | None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        **item.row,
        "sha256": item.document.sha256,
        "document_id": item.document.document_id,
        "output_dir": str(item.output_dir),
        "document_position": item.position,
        "status": status,
        "api_url": api_url,
        "error": error,
    }


def extract(
    *,
    api_urls: tuple[str, ...],
    manifest_path: Path,
    stop_event: threading.Event | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Extract inventory documents through MinerU's official Python client."""
    items = _load_manifest(manifest_path)
    settings.extraction_dir.mkdir(parents=True, exist_ok=True)
    manifests = ManifestStore()
    current_run_id = run_id or uuid.uuid4().hex
    stop = stop_event or threading.Event()

    reporter.start_progress(len(items))
    pending: list[tuple[WorkItem, str]] = []
    results: list[dict[str, Any]] = []
    reused = 0
    for item in items:
        persisted = manifests.load(item)
        if (
            _completed(item.output_dir)
            and persisted.status == "ok"
            and not settings.mineru_overwrite
        ):
            reused += 1
            results.append(
                _result_row(
                    item,
                    status="skipped",
                    api_url=persisted.api_url,
                )
            )
            continue
        pending.append((item, _document_stem(item)))
    reporter.restore_reused(reused)

    normalized_urls = tuple(
        dict.fromkeys(
            normalize_base_url(url.strip()) for url in api_urls if url.strip()
        )
    )
    if pending and len(normalized_urls) != 1:
        raise ValueError(
            "O cliente oficial MinerU usa um endpoint por execução. "
            "Informe uma única mineru-api ou um mineru-router que agregue "
            "as GPUs."
        )

    started = time.perf_counter()
    outcome: dict[str, Any] = {
        "installed": set(),
        "failures": [],
        "server_max_concurrent_requests": 0,
        "processing_window_size": 0,
        "effective_max_concurrent_requests": 0,
        "planned_task_count": 0,
        "peak_concurrency": 0,
    }
    if pending:
        outcome = asyncio.run(
            _orchestrate(
                api_url=normalized_urls[0],
                entries=pending,
                stop_event=stop,
            )
        )

    installed = set(outcome["installed"])
    failure_by_stem: dict[str, str] = {}
    for failure in outcome["failures"]:
        for stem in failure.document_stems:
            failure_by_stem[stem] = failure.message

    ok_count = 0
    error_count = 0
    completed_pages = 0
    for item, stem in pending:
        persisted = manifests.load(item)
        attempts = persisted.attempts + 1
        if stem in installed and _completed(item.output_dir):
            manifests.update(
                item,
                status="ok",
                attempts=attempts,
                retry_count=0,
                api_url=normalized_urls[0],
                task_id=None,
                correlation_key=current_run_id,
                duration_seconds=None,
                source_uri=None,
                artifact_uri=None,
                error=None,
                service={
                    "transport": "mineru-official-python-client",
                    "mineru_version": mineru_version,
                    "backend": settings.mineru_backend,
                    "parse_method": "auto",
                },
                controller={
                    "run_id": current_run_id,
                    "client_concurrency_cap": CLIENT_CONCURRENCY_CAP,
                    "server_max_concurrent_requests": outcome[
                        "server_max_concurrent_requests"
                    ],
                    "effective_max_concurrent_requests": outcome[
                        "effective_max_concurrent_requests"
                    ],
                    "processing_window_size": outcome["processing_window_size"],
                },
            )
            ok_count += 1
            completed_pages += item.document.page_count or 0
            results.append(
                _result_row(
                    item,
                    status="ok",
                    api_url=normalized_urls[0],
                )
            )
            reporter.document_finished(
                status="ok",
                pod_key=normalized_urls[0],
                sha256=item.document.sha256,
            )
            continue

        message = failure_by_stem.get(
            stem,
            "O cliente MinerU não devolveu um middle JSON válido.",
        )
        status = "pending" if stop.is_set() else "error"
        manifests.update(
            item,
            status=status,
            attempts=attempts,
            retry_count=0,
            api_url=normalized_urls[0],
            task_id=None,
            correlation_key=current_run_id,
            error=message,
        )
        if status == "error":
            error_count += 1
        results.append(
            _result_row(
                item,
                status=status,
                api_url=normalized_urls[0],
                error=message,
            )
        )
        reporter.document_finished(
            status="error",
            pod_key=normalized_urls[0],
            error=message,
            sha256=item.document.sha256,
        )

    elapsed = time.perf_counter() - started
    runs = pd.DataFrame(results)
    if not runs.empty:
        runs = runs.sort_values("document_position", kind="stable")
    _write_frame_atomic(runs, settings.extraction_dir / "runs.csv")
    errors = runs[~runs["status"].isin(("ok", "skipped"))] if not runs.empty else runs
    _write_frame_atomic(errors, settings.extraction_dir / "errors.csv")

    summary = {
        "run_id": current_run_id,
        "transport": "mineru-official-python-client",
        "mineru_version": mineru_version,
        "manifest_count": len(items),
        "eligible_count": len(items),
        "ok_count": ok_count,
        "completed_pages": completed_pages,
        "new_completed_pages": completed_pages,
        "new_completed_documents": ok_count,
        "reused_count": reused,
        "error_count": error_count,
        "remaining_count": len(pending) - ok_count,
        "retry_count": 0,
        "reconciled_count": 0,
        "reconciliation": {
            "enabled": False,
            "reason": "O cliente oficial recebe o ZIP na própria execução.",
        },
        "stopped_early": stop.is_set(),
        "api_url": normalized_urls[0] if normalized_urls else None,
        "client_concurrency_cap": CLIENT_CONCURRENCY_CAP,
        "server_max_concurrent_requests": outcome["server_max_concurrent_requests"],
        "effective_max_concurrent_requests": outcome[
            "effective_max_concurrent_requests"
        ],
        "processing_window_size": outcome["processing_window_size"],
        "planned_task_count": outcome["planned_task_count"],
        "peak_concurrency": outcome["peak_concurrency"],
        "pages_per_minute": round(
            completed_pages * 60 / max(elapsed, 0.001),
            2,
        ),
        "documents_per_minute": round(
            ok_count * 60 / max(elapsed, 0.001),
            2,
        ),
        "elapsed_seconds": round(elapsed, 3),
    }
    _write_json_atomic(settings.extraction_dir / "summary.json", summary)
    reporter.event(
        "Resumo | "
        f"concluídos={ok_count} | "
        f"reutilizados={reused} | "
        f"erros={error_count} | "
        f"restantes={summary['remaining_count']} | "
        f"vazão={summary['pages_per_minute']} pág/min",
        color="green" if not error_count else "yellow",
    )
    if error_count:
        raise RuntimeError(
            f"A extração MinerU falhou para {error_count} documento(s). "
            f"Consulte {settings.extraction_dir / 'errors.csv'}."
        )
    return summary
