# ---
# jupyter:
#   jupytext:
#     formats: py:percent,ipynb
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
# ---

# %% [markdown]
# # 02 — Executor MinerU remoto
#
# Executor de produção para processar o inventário completo em um conjunto
# variável de pods MinerU.
#
# A quantidade total de workers é determinada automaticamente:
#
#     total_workers = quantidade_de_pods * 8
#
# As URLs podem ser fornecidas como argumentos posicionais ou pela variável
# `MINERU_API_URLS`, separadas por vírgula, ponto e vírgula ou quebra de linha.
#
# Exemplo:
#
#     uv run python notebooks/02_mineru_smoke.py `
#       https://pod-1.proxy.runpod.net `
#       https://pod-2.proxy.runpod.net
#
# O executor:
#
# - valida todos os pods antes de começar;
# - mantém no máximo oito tarefas concorrentes por pod;
# - processa todo o manifesto por padrão;
# - retoma execuções sem reprocessar documentos concluídos;
# - redireciona retries para outros pods;
# - ignora `status_url` e `result_url` privados devolvidos pelo RunPod;
# - persiste o resultado de cada documento e relatórios consolidados.

# %%
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd


# %% [markdown]
# ## Configuração padrão

# %%
WORKERS_PER_POD = 8
BACKEND = "pipeline"

HEALTH_TIMEOUT_SECONDS = 30.0
SUBMIT_TIMEOUT_SECONDS = 300.0
TASK_POLL_INTERVAL_SECONDS = 1.0
TASK_TIMEOUT_SECONDS = 3600.0
RESULT_TIMEOUT_SECONDS = 300.0

DEFAULT_RETRIES = 2

PROJECT_ROOT = Path.cwd()
if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent

DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "inventory" / "inventory.csv"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "mineru" / "extraction"


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    api_urls: tuple[str, ...]
    manifest_path: Path
    output_root: Path
    workers_per_pod: int
    retries: int
    overwrite: bool
    limit: int | None

    @property
    def total_workers(self) -> int:
        return len(self.api_urls) * self.workers_per_pod


# %% [markdown]
# ## CLI

# %%
def split_api_urls(values: Sequence[str]) -> tuple[str, ...]:
    """Normaliza URLs recebidas por CLI ou variável de ambiente."""
    urls: list[str] = []
    for value in values:
        for candidate in re.split(r"[,;\s]+", value.strip()):
            candidate = candidate.strip().rstrip("/")
            if candidate and candidate not in urls:
                urls.append(candidate)
    return tuple(urls)


def parse_args(argv: Sequence[str] | None = None) -> ExecutorConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Processa PDFs em pods MinerU remotos usando oito workers por pod."
        )
    )
    parser.add_argument(
        "api_urls",
        nargs="*",
        help=(
            "URLs públicas dos pods. Quando omitidas, usa MINERU_API_URLS."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Manifesto CSV. Padrão: {DEFAULT_MANIFEST}",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Diretório de saída. Padrão: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--workers-per-pod",
        type=int,
        default=WORKERS_PER_POD,
        help="Concorrência por pod. Padrão operacional: 8.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="Quantidade de novas tentativas após a primeira execução.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Apaga e reprocessa saídas já concluídas.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita documentos apenas para diagnóstico. O padrão processa todos.",
    )

    args = parser.parse_args(argv)
    env_urls = os.environ.get("MINERU_API_URLS", "")
    api_urls = split_api_urls(args.api_urls or ([env_urls] if env_urls else []))

    if not api_urls:
        parser.error(
            "Informe ao menos uma URL de pod como argumento ou em MINERU_API_URLS."
        )
    if args.workers_per_pod < 1:
        parser.error("--workers-per-pod deve ser maior que zero.")
    if args.retries < 0:
        parser.error("--retries não pode ser negativo.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit deve ser maior que zero.")

    return ExecutorConfig(
        api_urls=api_urls,
        manifest_path=args.manifest.expanduser().resolve(),
        output_root=args.output_root.expanduser().resolve(),
        workers_per_pod=args.workers_per_pod,
        retries=args.retries,
        overwrite=args.overwrite,
        limit=args.limit,
    )


# %% [markdown]
# ## HTTP MinerU

# %%
def read_json_response(
    request: urllib.request.Request,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"MinerU respondeu HTTP {error.code}: {request.full_url}. "
            f"Resposta: {body[:1000]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Não foi possível acessar {request.full_url}: {error.reason}"
        ) from error

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Resposta inválida de {request.full_url}: {payload[:1000]}"
        ) from error

    if not isinstance(data, dict):
        raise TypeError(f"A resposta de {request.full_url} não é um objeto JSON.")
    return data


def get_api_health(api_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_url}/health",
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-MinerU-Executor/1.0",
        },
        method="GET",
    )
    return read_json_response(request, timeout_seconds=HEALTH_TIMEOUT_SECONDS)


def encode_multipart_form(
    *,
    pdf_path: Path,
    fields: dict[str, str],
) -> tuple[bytes, str]:
    boundary = f"----BaseIAMinerU{time.time_ns():x}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            'Content-Disposition: form-data; name="files"; '
            f'filename="{pdf_path.name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(pdf_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def submit_mineru_task(pdf_path: Path, api_url: str) -> dict[str, Any]:
    body, content_type = encode_multipart_form(
        pdf_path=pdf_path,
        fields={
            "backend": BACKEND,
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
            "User-Agent": "BaseIA-MinerU-Executor/1.0",
        },
        method="POST",
    )
    return read_json_response(request, timeout_seconds=SUBMIT_TIMEOUT_SECONDS)


def wait_for_mineru_task(api_url: str, task_id: str) -> dict[str, Any]:
    """Ignora status_url privado e reconstrói a URL pública."""
    status_url = f"{api_url}/tasks/{task_id}"
    deadline = time.monotonic() + TASK_TIMEOUT_SECONDS

    while True:
        request = urllib.request.Request(
            status_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BaseIA-MinerU-Executor/1.0",
            },
            method="GET",
        )
        payload = read_json_response(
            request,
            timeout_seconds=HEALTH_TIMEOUT_SECONDS,
        )
        status = str(payload.get("status", "")).lower()

        if status == "completed":
            return payload
        if status in {"failed", "error", "cancelled"}:
            raise RuntimeError(
                f"Tarefa {task_id} terminou com status {status!r}: "
                f"{payload.get('error') or payload}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Tarefa {task_id} excedeu {TASK_TIMEOUT_SECONDS:.0f} segundos."
            )
        time.sleep(TASK_POLL_INTERVAL_SECONDS)


def download_mineru_result(api_url: str, task_id: str) -> dict[str, Any]:
    """Ignora result_url privado e reconstrói a URL pública."""
    request = urllib.request.Request(
        f"{api_url}/tasks/{task_id}/result",
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-MinerU-Executor/1.0",
        },
        method="GET",
    )
    return read_json_response(request, timeout_seconds=RESULT_TIMEOUT_SECONDS)


# %% [markdown]
# ## Persistência

# %%
def safe_directory_name(row: pd.Series) -> str:
    for key in ("document_id", "sha256"):
        value = str(row.get(key) or "").strip()
        if value and value.lower() != "nan":
            return value if key == "document_id" else value[:16]
    return Path(str(row["path"])).stem


def count_generated_files(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0
    return sum(1 for path in output_dir.rglob("*") if path.is_file())


def has_completed_output(output_dir: Path) -> bool:
    return output_dir.exists() and any(output_dir.rglob("*_middle.json"))


def save_mineru_result(result: dict[str, Any], output_dir: Path) -> None:
    results = result.get("results")
    if not isinstance(results, dict) or not results:
        raise ValueError("A resposta MinerU não contém resultados.")

    output_dir.mkdir(parents=True, exist_ok=True)
    saved_middle_json = False

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
            with (document_dir / f"{document_name}_middle.json").open(
                "w", encoding="utf-8"
            ) as file:
                json.dump(middle_json, file, ensure_ascii=False, indent=2)
            saved_middle_json = True

    with (output_dir / "api_result.json").open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    if not saved_middle_json:
        raise ValueError("O resultado não produziu nenhum middle JSON.")


def append_json_line(path: Path, payload: dict[str, Any], lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


# %% [markdown]
# ## Execução de documentos

# %%
def run_single_attempt(
    *,
    pdf_path: Path,
    output_dir: Path,
    log_path: Path,
    api_url: str,
    pod_number: int,
    attempt: int,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    started_counter = time.perf_counter()

    submission = submit_mineru_task(pdf_path, api_url)
    task_id = submission.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError(f"A submissão não devolveu task_id: {submission}")

    append_json_line(
        log_path,
        {
            "event": "submitted",
            "attempt": attempt,
            "pod_number": pod_number,
            "api_url": api_url,
            "task_id": task_id,
            "timestamp": started_at.isoformat(),
        },
        threading.Lock(),
    )

    status_payload = wait_for_mineru_task(api_url, task_id)
    result = download_mineru_result(api_url, task_id)
    save_mineru_result(result, output_dir)

    duration = time.perf_counter() - started_counter
    completed_at = datetime.now(timezone.utc)
    return {
        "status": "ok",
        "task_id": task_id,
        "attempts": attempt,
        "pod_number": pod_number,
        "api_url": api_url,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round(duration, 3),
        "generated_files": count_generated_files(output_dir),
        "error": None,
    }


def process_document(
    *,
    position: int,
    total_documents: int,
    row: pd.Series,
    initial_pod_index: int,
    config: ExecutorConfig,
    pod_semaphores: dict[str, threading.Semaphore],
    log_lock: threading.Lock,
) -> dict[str, Any]:
    pdf_path = Path(str(row["path"])).expanduser().resolve()
    document_key = safe_directory_name(row)
    output_dir = config.output_root / "documents" / document_key
    log_path = output_dir / "mineru.log.jsonl"

    page_count = pd.to_numeric(
        pd.Series([row.get("page_count")]), errors="coerce"
    ).iloc[0]
    base = {
        "document_position": position,
        "document_id": row.get("document_id"),
        "sha256": row.get("sha256"),
        "filename": row.get("filename"),
        "path": str(pdf_path),
        "page_count": page_count,
        "size_mb": row.get("size_mb"),
        "backend": BACKEND,
        "output_dir": str(output_dir),
        "log_path": str(log_path),
    }

    if not pdf_path.exists():
        return {
            **base,
            "status": "error",
            "attempts": 0,
            "generated_files": 0,
            "error": "Arquivo PDF não encontrado",
        }

    if has_completed_output(output_dir) and not config.overwrite:
        return {
            **base,
            "status": "skipped",
            "attempts": 0,
            "generated_files": count_generated_files(output_dir),
            "error": None,
        }

    if output_dir.exists() and config.overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for attempt in range(1, config.retries + 2):
        pod_index = (initial_pod_index + attempt - 1) % len(config.api_urls)
        api_url = config.api_urls[pod_index]
        pod_number = pod_index + 1

        try:
            with pod_semaphores[api_url]:
                print(
                    f"[{position + 1:04d}/{total_documents:04d}] "
                    f"pod={pod_number} tentativa={attempt} | {pdf_path.name}"
                )
                run = run_single_attempt(
                    pdf_path=pdf_path,
                    output_dir=output_dir,
                    log_path=log_path,
                    api_url=api_url,
                    pod_number=pod_number,
                    attempt=attempt,
                )
            duration = run.get("duration_seconds")
            seconds_per_page = None
            if duration is not None and pd.notna(page_count) and float(page_count) > 0:
                seconds_per_page = round(float(duration) / float(page_count), 4)
            return {**base, **run, "seconds_per_page": seconds_per_page}
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            errors.append(f"pod={pod_number} tentativa={attempt}: {message}")
            append_json_line(
                log_path,
                {
                    "event": "attempt_failed",
                    "attempt": attempt,
                    "pod_number": pod_number,
                    "api_url": api_url,
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                log_lock,
            )

    return {
        **base,
        "status": "error",
        "attempts": config.retries + 1,
        "generated_files": count_generated_files(output_dir),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error": " | ".join(errors),
        "seconds_per_page": None,
    }


# %% [markdown]
# ## Executor

# %%
def load_manifest(config: ExecutorConfig) -> pd.DataFrame:
    if not config.manifest_path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {config.manifest_path}")

    manifest = pd.read_csv(config.manifest_path).reset_index(drop=True)
    required = {"path", "filename", "page_count"}
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Colunas ausentes no manifesto: {sorted(missing)}")
    if manifest.empty:
        raise RuntimeError("O manifesto está vazio.")
    if config.limit is not None:
        manifest = manifest.head(config.limit).copy()
    return manifest


def validate_pods(config: ExecutorConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pod_number, api_url in enumerate(config.api_urls, start=1):
        started = time.perf_counter()
        try:
            health = get_api_health(api_url)
            rows.append(
                {
                    "pod_number": pod_number,
                    "api_url": api_url,
                    "status": "ok",
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "health": health,
                    "error": None,
                }
            )
        except Exception as error:
            rows.append(
                {
                    "pod_number": pod_number,
                    "api_url": api_url,
                    "status": "error",
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "health": None,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

    failed = [row for row in rows if row["status"] != "ok"]
    if failed:
        details = "\n".join(
            f"- {row['api_url']}: {row['error']}" for row in failed
        )
        raise RuntimeError(f"Pods indisponíveis no health check:\n{details}")
    return rows


def persist_runs(runs: list[dict[str, Any]], config: ExecutorConfig) -> pd.DataFrame:
    runs_df = pd.DataFrame(runs)
    if not runs_df.empty:
        runs_df = runs_df.sort_values("document_position").reset_index(drop=True)
    runs_df.to_csv(config.output_root / "runs.csv", index=False, encoding="utf-8-sig")
    try:
        runs_df.to_parquet(config.output_root / "runs.parquet", index=False)
    except (ImportError, ValueError):
        pass
    return runs_df


def execute(config: ExecutorConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    config.output_root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(config)
    health_rows = validate_pods(config)
    write_path = config.output_root / "pods.json"
    write_path.write_text(
        json.dumps(health_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Pods: {len(config.api_urls)}")
    print(f"Workers por pod: {config.workers_per_pod}")
    print(f"Workers totais: {config.total_workers}")
    print(f"Documentos: {len(manifest)}")
    print(f"Saída: {config.output_root}")

    pod_semaphores = {
        url: threading.Semaphore(config.workers_per_pod) for url in config.api_urls
    }
    log_lock = threading.Lock()
    runs: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc)
    started_counter = time.perf_counter()

    with ThreadPoolExecutor(max_workers=config.total_workers) as executor:
        futures = {
            executor.submit(
                process_document,
                position=position,
                total_documents=len(manifest),
                row=row.copy(),
                initial_pod_index=position % len(config.api_urls),
                config=config,
                pod_semaphores=pod_semaphores,
                log_lock=log_lock,
            ): position
            for position, row in manifest.iterrows()
        }

        for completed_count, future in enumerate(as_completed(futures), start=1):
            position = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "document_position": position,
                    "status": "error",
                    "error": f"Falha não tratada: {type(error).__name__}: {error}",
                }
            runs.append(result)
            persist_runs(runs, config)
            print(
                f"Concluídos: {completed_count}/{len(manifest)} | "
                f"ok={sum(row.get('status') == 'ok' for row in runs)} "
                f"skip={sum(row.get('status') == 'skipped' for row in runs)} "
                f"erro={sum(row.get('status') == 'error' for row in runs)}"
            )

    elapsed = time.perf_counter() - started_counter
    runs_df = persist_runs(runs, config)
    ok_df = runs_df[runs_df["status"] == "ok"] if not runs_df.empty else runs_df
    total_pages = pd.to_numeric(ok_df.get("page_count"), errors="coerce").sum()
    throughput = float(total_pages) / elapsed * 60 if elapsed > 0 else None

    summary = {
        "pod_count": len(config.api_urls),
        "workers_per_pod": config.workers_per_pod,
        "total_workers": config.total_workers,
        "document_count": len(manifest),
        "ok_count": int((runs_df["status"] == "ok").sum()),
        "skipped_count": int((runs_df["status"] == "skipped").sum()),
        "error_count": int((runs_df["status"] == "error").sum()),
        "total_pages_ok": float(total_pages),
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "pages_per_minute": round(throughput, 3) if throughput is not None else None,
        "manifest_path": str(config.manifest_path),
        "output_root": str(config.output_root),
        "api_urls": list(config.api_urls),
    }
    (config.output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    errors_df = runs_df[runs_df["status"] == "error"].copy()
    errors_df.to_csv(
        config.output_root / "errors.csv", index=False, encoding="utf-8-sig"
    )
    return runs_df, summary


# %%
def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    _, summary = execute(config)

    print("\nExtração concluída.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
