from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .settings import settings


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    api_urls: tuple[str, ...]
    manifest_path: Path
    output_root: Path
    workers_per_pod: int
    retries: int
    overwrite: bool

    @property
    def total_workers(self) -> int:
        return len(self.api_urls) * self.workers_per_pod


def _read_json(
    request: urllib.request.Request,
    timeout: float,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"MinerU respondeu HTTP {error.code}: "
            f"{request.full_url}. {body[:1000]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Não foi possível acessar {request.full_url}: {error.reason}"
        ) from error

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"MinerU retornou JSON inválido em {request.full_url}: "
            f"{payload[:1000]}"
        ) from error

    if not isinstance(data, dict):
        raise TypeError(f"Resposta inválida de {request.full_url}")
    return data


def _multipart(
    pdf_path: Path,
    fields: dict[str, str],
) -> tuple[bytes, str]:
    boundary = f"----BaseIAMinerU{time.time_ns():x}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="{name}"'
                f"\r\n\r\n{value}\r\n"
            ).encode()
        )

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            'Content-Disposition: form-data; name="files"; '
            f'filename="{pdf_path.name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
    )
    body.extend(pdf_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _health(api_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_url}/health",
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-Extract/1.0",
        },
        method="GET",
    )
    return _read_json(request, settings.mineru_health_timeout_seconds)


def _submit(
    pdf_path: Path,
    api_url: str,
) -> dict[str, Any]:
    body, content_type = _multipart(
        pdf_path,
        {
            "backend": settings.mineru_backend,
            "parse_method": "auto",
            "formula_enable": "true",
            "table_enable": "true",
            "return_md": "true",
            "return_middle_json": "true",
            "return_model_output": "false",
            "return_content_list": "false",
            "return_images": "false",
            "response_format_zip": "false",
        },
    )
    request = urllib.request.Request(
        f"{api_url}/tasks",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "BaseIA-Extract/1.0",
        },
        method="POST",
    )
    return _read_json(request, settings.mineru_submit_timeout_seconds)


def _wait(api_url: str, task_id: str) -> None:
    deadline = time.monotonic() + settings.mineru_task_timeout_seconds
    url = f"{api_url}/tasks/{task_id}"

    while True:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BaseIA-Extract/1.0",
            },
            method="GET",
        )
        payload = _read_json(
            request,
            settings.mineru_health_timeout_seconds,
        )
        status = str(payload.get("status", "")).lower()

        if status == "completed":
            return
        if status in {"failed", "error", "cancelled"}:
            raise RuntimeError(
                f"Tarefa {task_id} terminou com status {status}: {payload}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Tarefa {task_id} excedeu o timeout.")

        time.sleep(settings.mineru_poll_interval_seconds)


def _download(
    api_url: str,
    task_id: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_url}/tasks/{task_id}/result",
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-Extract/1.0",
        },
        method="GET",
    )
    return _read_json(request, settings.mineru_result_timeout_seconds)


def _save_result(
    result: dict[str, Any],
    output_dir: Path,
) -> None:
    results = result.get("results")
    if not isinstance(results, dict) or not results:
        raise ValueError("Resultado MinerU sem documentos.")

    saved_middle_json = False
    output_dir.mkdir(parents=True, exist_ok=True)

    for document_name, document_result in results.items():
        if not isinstance(document_result, dict):
            continue

        document_dir = output_dir / str(document_name)
        document_dir.mkdir(parents=True, exist_ok=True)

        md_content = document_result.get("md_content")
        if isinstance(md_content, str):
            (document_dir / f"{document_name}.md").write_text(
                md_content,
                encoding="utf-8",
            )

        middle_json = document_result.get("middle_json")
        if isinstance(middle_json, str):
            try:
                middle_json = json.loads(middle_json)
            except json.JSONDecodeError:
                pass

        if middle_json is not None:
            (document_dir / f"{document_name}_middle.json").write_text(
                json.dumps(
                    middle_json,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            saved_middle_json = True

    (output_dir / "api_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not saved_middle_json:
        raise ValueError("Resultado sem middle JSON.")


def _completed(output_dir: Path) -> bool:
    middle_paths = list(output_dir.rglob("*_middle.json"))
    if len(middle_paths) != 1:
        return False

    try:
        payload = json.loads(
            middle_paths[0].read_text(encoding="utf-8")
        )
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


def _document_key(row: pd.Series) -> str:
    for key in ("document_id", "sha256"):
        value = str(row.get(key) or "").strip()
        if value and value.lower() != "nan":
            return value if key == "document_id" else value[:16]

    return Path(str(row["path"])).stem


def _process(
    position: int,
    total: int,
    row: pd.Series,
    config: ExtractionConfig,
    semaphores: dict[str, threading.Semaphore],
) -> dict[str, Any]:
    pdf_path = Path(str(row["path"])).expanduser().resolve()
    output_dir = config.output_root / "documents" / _document_key(row)

    base = {
        "document_position": position,
        "document_id": row.get("document_id"),
        "sha256": row.get("sha256"),
        "filename": row.get("filename"),
        "path": str(pdf_path),
        "page_count": row.get("page_count"),
        "output_dir": str(output_dir),
    }

    if not pdf_path.exists():
        return {
            **base,
            "status": "error",
            "error": "Arquivo PDF não encontrado",
        }

    completed = _completed(output_dir)
    if completed and not config.overwrite:
        return {
            **base,
            "status": "skipped",
            "error": None,
        }

    if output_dir.exists() and (config.overwrite or not completed):
        shutil.rmtree(output_dir)

    errors: list[str] = []
    for attempt in range(config.retries + 1):
        pod_index = (position + attempt) % len(config.api_urls)
        api_url = config.api_urls[pod_index]

        try:
            with semaphores[api_url]:
                print(
                    f"[{position + 1:04d}/{total:04d}] "
                    f"pod={pod_index + 1} | {pdf_path.name}"
                )
                started = time.perf_counter()
                submission = _submit(pdf_path, api_url)
                task_id = submission.get("task_id")

                if not isinstance(task_id, str) or not task_id:
                    raise ValueError(
                        f"Submissão sem task_id: {submission}"
                    )

                _wait(api_url, task_id)
                _save_result(
                    _download(api_url, task_id),
                    output_dir,
                )

                return {
                    **base,
                    "status": "ok",
                    "task_id": task_id,
                    "pod_number": pod_index + 1,
                    "api_url": api_url,
                    "attempts": attempt + 1,
                    "duration_seconds": round(
                        time.perf_counter() - started,
                        3,
                    ),
                    "error": None,
                }
        except Exception as error:
            errors.append(
                f"pod={pod_index + 1}: "
                f"{type(error).__name__}: {error}"
            )

    return {
        **base,
        "status": "error",
        "attempts": config.retries + 1,
        "error": " | ".join(errors),
    }


def _load_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {path}")

    manifest = pd.read_csv(path).reset_index(drop=True)
    required = {
        "document_id",
        "sha256",
        "path",
        "filename",
        "page_count",
    }
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(
            f"Colunas ausentes no manifesto: {sorted(missing)}"
        )

    if "status" in manifest.columns:
        manifest = manifest[manifest["status"].astype(str).eq("ok")].copy()

    manifest["document_id"] = manifest["document_id"].astype(str)
    manifest = (
        manifest[manifest["document_id"].ne("")]
        .drop_duplicates("document_id", keep="first")
        .reset_index(drop=True)
    )

    if manifest.empty:
        raise RuntimeError("Manifesto vazio.")

    return manifest


def _execute(config: ExtractionConfig) -> dict[str, Any]:
    manifest = _load_manifest(config.manifest_path)

    if not config.api_urls:
        raise ValueError("Nenhuma URL MinerU foi fornecida.")

    config.output_root.mkdir(parents=True, exist_ok=True)

    health = [
        {
            "pod_number": index,
            "api_url": url,
            "health": _health(url),
        }
        for index, url in enumerate(config.api_urls, start=1)
    ]
    (config.output_root / "pods.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    semaphores = {
        url: threading.Semaphore(config.workers_per_pod)
        for url in config.api_urls
    }
    runs: list[dict[str, Any]] = []
    started = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=config.total_workers,
    ) as executor:
        futures = {
            executor.submit(
                _process,
                position,
                len(manifest),
                row.copy(),
                config,
                semaphores,
            ): position
            for position, row in manifest.iterrows()
        }

        for future in as_completed(futures):
            runs.append(future.result())
            pd.DataFrame(runs).sort_values(
                "document_position"
            ).to_csv(
                config.output_root / "runs.csv",
                index=False,
                encoding="utf-8-sig",
            )

    runs_df = (
        pd.DataFrame(runs)
        .sort_values("document_position")
        .reset_index(drop=True)
    )
    ok_df = runs_df[runs_df["status"].eq("ok")]
    elapsed = time.perf_counter() - started
    pages = pd.to_numeric(
        ok_df.get("page_count"),
        errors="coerce",
    ).sum()

    summary = {
        "pod_count": len(config.api_urls),
        "workers_per_pod": config.workers_per_pod,
        "total_workers": config.total_workers,
        "document_count": len(runs_df),
        "ok_count": int(runs_df["status"].eq("ok").sum()),
        "skipped_count": int(
            runs_df["status"].eq("skipped").sum()
        ),
        "error_count": int(runs_df["status"].eq("error").sum()),
        "elapsed_seconds": round(elapsed, 3),
        "pages_per_minute": (
            round(float(pages) / elapsed * 60, 3)
            if elapsed
            else None
        ),
    }
    (config.output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    runs_df[runs_df["status"].eq("error")].to_csv(
        config.output_root / "errors.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def extract(
    *,
    api_urls: tuple[str, ...],
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Executa o MinerU nos pods já provisionados pela camada de tarefas."""
    config = ExtractionConfig(
        api_urls=api_urls,
        manifest_path=manifest_path or settings.inventory_path,
        output_root=settings.mineru_output_dir,
        workers_per_pod=settings.mineru_workers_per_pod,
        retries=settings.mineru_retries,
        overwrite=settings.mineru_overwrite,
    )

    if config.workers_per_pod < 1:
        raise ValueError("workers_per_pod deve ser maior que zero.")

    return _execute(config)
