# ---
# jupyter:
#   jupytext:
#     formats: py:percent,ipynb
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Benchmark MinerU remoto — 3 pods, de 3 a 24 workers
#
# Este notebook mede o throughput do MinerU com três APIs remotas.
#
# Para cada rodada, ele usa:
#
# - 3, 6, 9, 12, 15, 18, 21 e 24 workers totais;
# - distribuição round-robin entre os três pods;
# - limite de 1 a 8 chamadas simultâneas por pod;
# - diretório de saída separado por rodada;
# - CSV e Parquet separados por rodada;
# - resumo consolidado de tempo, páginas por minuto e erros.
#
# Cada `mineru-api` remoto deve estar configurado para aceitar pelo menos
# oito requisições concorrentes na rodada de 24 workers.

# %%
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from IPython.display import display

pd.set_option("display.max_columns", 100)
pd.set_option("display.max_colwidth", 160)
pd.set_option("display.width", 220)

# %% [markdown]
# ## 1. Caminhos

# %%
PROJECT_ROOT = Path.cwd()

if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent


SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "samples" / "benchmark_sample.csv"

MINERU_EXE = PROJECT_ROOT / ".venv-mineru" / "Scripts" / "mineru.exe"

OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "mineru" / "worker_benchmark"

SUMMARY_CSV_PATH = OUTPUT_ROOT / "benchmark_summary.csv"
SUMMARY_PARQUET_PATH = OUTPUT_ROOT / "benchmark_summary.parquet"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

print(f"MinerU: {MINERU_EXE}")
print(f"Manifesto: {SAMPLE_MANIFEST}")
print(f"Saída: {OUTPUT_ROOT}")

# %% [markdown]
# ## 2. Configuração
#
# Os valores de `WORKER_COUNTS` são múltiplos de três para manter a mesma
# capacidade por pod:
#
# - 3 workers = 1 por pod;
# - 6 workers = 2 por pod;
# - ...
# - 24 workers = 8 por pod.

# %%
BACKEND = "pipeline"

API_URLS = (
    "https://00e1vcjtxavr7w-8000.proxy.runpod.net",
    "https://8wddd5b6crg0c3-8000.proxy.runpod.net",
    "https://0zgf7sp4qhvuc7-8000.proxy.runpod.net",
)

WORKER_COUNTS = tuple(range(3, 25, 3))

TEST_SLICE = 24
OVERWRITE_BENCHMARK_OUTPUTS = True
HEALTH_TIMEOUT_SECONDS = 30.0

# O CLI pode ficar muito tempo aguardando um PDF grande.
# `None` desativa timeout do subprocesso.
PROCESS_TIMEOUT_SECONDS: float | None = None

print(f"Pods: {len(API_URLS)}")
print(f"Rodadas: {WORKER_COUNTS}")
print(f"Documentos por rodada: {TEST_SLICE}")

# %% [markdown]
# ## 3. Validação inicial

# %%
if not MINERU_EXE.exists():
    raise FileNotFoundError(f"Executável do MinerU não encontrado: {MINERU_EXE}")

if not SAMPLE_MANIFEST.exists():
    raise FileNotFoundError(f"Manifesto não encontrado: {SAMPLE_MANIFEST}")

if len(API_URLS) != 3:
    raise ValueError("Este benchmark foi preparado para exatamente três pods.")

if any(worker_count % len(API_URLS) != 0 for worker_count in WORKER_COUNTS):
    raise ValueError(
        "Todos os valores de WORKER_COUNTS devem ser múltiplos do número de pods."
    )

if max(WORKER_COUNTS) // len(API_URLS) > 8:
    raise ValueError("A configuração excede oito chamadas simultâneas por pod.")

sample = pd.read_csv(SAMPLE_MANIFEST).head(TEST_SLICE).reset_index(drop=True)

if sample.empty:
    raise RuntimeError("A amostra está vazia.")

required_columns = {"path", "filename", "page_count"}
missing_columns = required_columns.difference(sample.columns)

if missing_columns:
    raise ValueError(f"Colunas ausentes no manifesto: {sorted(missing_columns)}")

print(f"Documentos carregados: {len(sample)}")

display(
    sample[
        [
            "filename",
            "page_count",
            "size_mb",
            "path",
        ]
    ]
)

# %% [markdown]
# ## 4. Health check dos três pods


# %%
def get_api_health(
    api_url: str,
    timeout_seconds: float = HEALTH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    health_url = f"{api_url.rstrip('/')}/health"

    request = urllib.request.Request(
        health_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BaseIA-MinerU-HealthCheck/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"MinerU API respondeu HTTP {error.code}: {health_url}. "
            f"Resposta: {body[:500]}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Não foi possível acessar {health_url}: {error.reason}"
        ) from error

    data = json.loads(payload)

    if not isinstance(data, dict):
        raise TypeError(f"A resposta de {health_url} não é um objeto JSON.")

    return data


health_rows: list[dict[str, Any]] = []

for pod_index, api_url in enumerate(API_URLS, start=1):
    try:
        health = get_api_health(api_url)
        health_rows.append(
            {
                "pod": pod_index,
                "api_url": api_url,
                "status": "ok",
                "error": None,
                "health": health,
            }
        )
    except Exception as error:
        health_rows.append(
            {
                "pod": pod_index,
                "api_url": api_url,
                "status": "error",
                "error": f"{type(error).__name__}: {error}",
                "health": None,
            }
        )

health_df = pd.DataFrame(health_rows)
display(health_df[["pod", "api_url", "status", "error"]])

if not health_df["status"].eq("ok").all():
    raise RuntimeError(
        "Ao menos um pod falhou no health check. Corrija antes do benchmark."
    )

# %% [markdown]
# ## 5. Funções auxiliares


# %%
def safe_directory_name(row: pd.Series) -> str:
    document_id = str(row.get("document_id") or "").strip()
    sha256 = str(row.get("sha256") or "").strip()

    if document_id and document_id.lower() != "nan":
        return document_id

    if sha256 and sha256.lower() != "nan":
        return sha256[:16]

    return Path(str(row["path"])).stem


def count_generated_files(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0

    return sum(1 for path in output_dir.rglob("*") if path.is_file())


def has_completed_output(output_dir: Path) -> bool:
    return output_dir.exists() and any(output_dir.rglob("*_middle.json"))


# %% [markdown]
# ## 6. Execução de uma chamada MinerU
#
# O stdout do processo é gravado diretamente no log do documento. Isso evita
# deadlock por buffer cheio e impede que logs de vários workers se misturem no
# notebook.


# %%
def run_mineru(
    pdf_path: Path,
    output_dir: Path,
    log_path: Path,
    api_url: str,
) -> dict[str, object]:
    command = [
        str(MINERU_EXE),
        "-p",
        str(pdf_path),
        "-o",
        str(output_dir),
        "--api-url",
        api_url,
        "--backend",
        BACKEND,
    ]

    started_at = datetime.now(timezone.utc)
    started_counter = time.perf_counter()

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as log_file:
        log_file.write(subprocess.list2cmdline(command))
        log_file.write("\n\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        try:
            return_code = process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise TimeoutError(
                f"MinerU excedeu o timeout para {pdf_path.name}."
            ) from error

    duration_seconds = time.perf_counter() - started_counter
    completed_at = datetime.now(timezone.utc)

    return {
        "status": "ok" if return_code == 0 else "error",
        "return_code": return_code,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round(duration_seconds, 3),
        "output_dir": str(output_dir.resolve()),
        "log_path": str(log_path.resolve()),
        "generated_files": count_generated_files(output_dir),
    }


# %% [markdown]
# ## 7. Processamento de um documento


# %%
def process_document(
    document_position: int,
    row: pd.Series,
    *,
    api_url: str,
    pod_number: int,
    benchmark_output_root: Path,
    pod_semaphore: threading.Semaphore,
) -> dict[str, object]:
    pdf_path = Path(str(row["path"])).expanduser().resolve()
    document_key = safe_directory_name(row)

    document_output = benchmark_output_root / "documents" / document_key
    log_path = document_output / "mineru.log"

    base_result: dict[str, object] = {
        "document_position": document_position,
        "document_id": row.get("document_id"),
        "sha256": row.get("sha256"),
        "filename": row.get("filename"),
        "path": str(pdf_path),
        "page_count": pd.to_numeric(
            pd.Series([row.get("page_count")]),
            errors="coerce",
        ).iloc[0],
        "size_mb": row.get("size_mb"),
        "pod_number": pod_number,
        "api_url": api_url,
        "backend": BACKEND,
    }

    if not pdf_path.exists():
        return {
            **base_result,
            "status": "error",
            "return_code": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "output_dir": str(document_output.resolve()),
            "log_path": str(log_path.resolve()),
            "generated_files": 0,
            "error": "Arquivo PDF não encontrado",
            "seconds_per_page": None,
        }

    if has_completed_output(document_output) and not OVERWRITE_BENCHMARK_OUTPUTS:
        return {
            **base_result,
            "status": "skipped",
            "return_code": 0,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "output_dir": str(document_output.resolve()),
            "log_path": str(log_path.resolve()),
            "generated_files": count_generated_files(document_output),
            "error": None,
            "seconds_per_page": None,
        }

    try:
        with pod_semaphore:
            print(
                f"[{document_position + 1:02d}/{len(sample):02d}] "
                f"pod={pod_number} | {pdf_path.name}"
            )

            run = run_mineru(
                pdf_path=pdf_path,
                output_dir=document_output,
                log_path=log_path,
                api_url=api_url,
            )

        run["error"] = None

    except Exception as error:
        run = {
            "status": "error",
            "return_code": None,
            "started_at": None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": None,
            "output_dir": str(document_output.resolve()),
            "log_path": str(log_path.resolve()),
            "generated_files": count_generated_files(document_output),
            "error": f"{type(error).__name__}: {error}",
        }

    duration = run.get("duration_seconds")
    page_count = base_result["page_count"]
    seconds_per_page = None

    if duration is not None and pd.notna(page_count) and float(page_count) > 0:
        seconds_per_page = round(
            float(duration) / float(page_count),
            4,
        )

    return {
        **base_result,
        **run,
        "seconds_per_page": seconds_per_page,
    }


# %% [markdown]
# ## 8. Execução de uma rodada
#
# O semáforo por pod garante que a rodada de 24 workers nunca envie mais de
# oito chamadas simultâneas para uma mesma API.


# %%
def run_benchmark(worker_count: int) -> tuple[pd.DataFrame, dict[str, object]]:
    if worker_count % len(API_URLS) != 0:
        raise ValueError("worker_count deve ser múltiplo do número de pods.")

    requests_per_pod = worker_count // len(API_URLS)

    benchmark_output_root = OUTPUT_ROOT / f"workers_{worker_count:02d}"

    if benchmark_output_root.exists() and OVERWRITE_BENCHMARK_OUTPUTS:
        shutil.rmtree(benchmark_output_root)

    benchmark_output_root.mkdir(parents=True, exist_ok=True)

    runs_path = benchmark_output_root / "runs.parquet"
    runs_csv_path = benchmark_output_root / "runs.csv"

    pod_semaphores = {
        api_url: threading.Semaphore(requests_per_pod) for api_url in API_URLS
    }

    runs: list[dict[str, object]] = []
    started_at = datetime.now(timezone.utc)
    started_counter = time.perf_counter()

    print()
    print("=" * 100)
    print(f"RODADA: {worker_count} workers totais | {requests_per_pod} por pod")
    print("=" * 100)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}

        for document_position, row in sample.iterrows():
            pod_index = document_position % len(API_URLS)
            api_url = API_URLS[pod_index]

            future = executor.submit(
                process_document,
                document_position,
                row.copy(),
                api_url=api_url,
                pod_number=pod_index + 1,
                benchmark_output_root=benchmark_output_root,
                pod_semaphore=pod_semaphores[api_url],
            )

            futures[future] = document_position

        for completed_count, future in enumerate(
            as_completed(futures),
            start=1,
        ):
            document_position = futures[future]

            try:
                result = future.result()
            except Exception as error:
                result = {
                    "document_position": document_position,
                    "document_id": None,
                    "sha256": None,
                    "filename": None,
                    "path": None,
                    "page_count": None,
                    "size_mb": None,
                    "pod_number": None,
                    "api_url": None,
                    "backend": BACKEND,
                    "status": "error",
                    "return_code": None,
                    "started_at": None,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": None,
                    "output_dir": None,
                    "log_path": None,
                    "generated_files": 0,
                    "error": (
                        f"Falha não tratada no documento {document_position}: "
                        f"{type(error).__name__}: {error}"
                    ),
                    "seconds_per_page": None,
                }

            runs.append(result)

            runs_df = (
                pd.DataFrame(runs)
                .sort_values("document_position")
                .reset_index(drop=True)
            )

            runs_df.to_parquet(runs_path, index=False)
            runs_df.to_csv(
                runs_csv_path,
                index=False,
                encoding="utf-8-sig",
            )

            print(
                f"Concluídos: {completed_count}/{len(sample)} | "
                f"último status: {result['status']}"
            )

    elapsed_seconds = time.perf_counter() - started_counter
    completed_at = datetime.now(timezone.utc)

    runs_df = pd.DataFrame(runs).sort_values("document_position").reset_index(drop=True)

    ok_df = runs_df[runs_df["status"] == "ok"].copy()
    skipped_df = runs_df[runs_df["status"] == "skipped"].copy()
    error_df = runs_df[runs_df["status"] == "error"].copy()

    total_pages = pd.to_numeric(
        ok_df["page_count"],
        errors="coerce",
    ).sum()

    pages_per_minute = (
        float(total_pages) / elapsed_seconds * 60 if elapsed_seconds > 0 else None
    )

    summary = {
        "worker_count": worker_count,
        "pod_count": len(API_URLS),
        "requests_per_pod": requests_per_pod,
        "document_count": len(sample),
        "ok_count": len(ok_df),
        "skipped_count": len(skipped_df),
        "error_count": len(error_df),
        "total_pages_ok": float(total_pages),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "pages_per_minute": (
            round(pages_per_minute, 3) if pages_per_minute is not None else None
        ),
        "mean_document_seconds": (
            round(ok_df["duration_seconds"].mean(), 3) if not ok_df.empty else None
        ),
        "median_document_seconds": (
            round(ok_df["duration_seconds"].median(), 3) if not ok_df.empty else None
        ),
        "runs_path": str(runs_path.resolve()),
        "runs_csv_path": str(runs_csv_path.resolve()),
    }

    print()
    print(f"Workers: {worker_count}")
    print(f"Requests por pod: {requests_per_pod}")
    print(f"Tempo total: {elapsed_seconds:.2f} s")
    print(f"Páginas concluídas: {total_pages:.0f}")
    print(f"Throughput: {pages_per_minute:.2f} páginas/min")
    print(f"Erros: {len(error_df)}")

    return runs_df, summary


# %% [markdown]
# ## 9. Executar todas as rodadas
#
# Cada rodada processa os mesmos 24 documentos em um diretório independente.

# %%
benchmark_summaries: list[dict[str, object]] = []
benchmark_runs: dict[int, pd.DataFrame] = {}

for worker_count in WORKER_COUNTS:
    runs_df, summary = run_benchmark(worker_count)

    benchmark_runs[worker_count] = runs_df
    benchmark_summaries.append(summary)

    benchmark_summary_df = pd.DataFrame(benchmark_summaries)

    benchmark_summary_df.to_csv(
        SUMMARY_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    benchmark_summary_df.to_parquet(
        SUMMARY_PARQUET_PATH,
        index=False,
    )

# %% [markdown]
# ## 10. Resultado consolidado

# %%
benchmark_summary_df = (
    pd.DataFrame(benchmark_summaries).sort_values("worker_count").reset_index(drop=True)
)

benchmark_summary_df[
    [
        "worker_count",
        "requests_per_pod",
        "ok_count",
        "error_count",
        "total_pages_ok",
        "elapsed_seconds",
        "pages_per_minute",
        "mean_document_seconds",
        "median_document_seconds",
    ]
]

# %%
best_successful = benchmark_summary_df[
    benchmark_summary_df["error_count"] == 0
].sort_values(
    "pages_per_minute",
    ascending=False,
)

if best_successful.empty:
    print("Nenhuma rodada terminou sem erros.")
else:
    best_row = best_successful.iloc[0]

    print(
        "Melhor rodada sem erros: "
        f"{int(best_row['worker_count'])} workers, "
        f"{best_row['pages_per_minute']:.2f} páginas/min."
    )

# %% [markdown]
# ## 11. Distribuição de resultados por pod

# %%
pod_summary_rows: list[dict[str, object]] = []

for worker_count, runs_df in benchmark_runs.items():
    grouped = (
        runs_df.groupby(
            ["pod_number", "api_url"],
            dropna=False,
        )
        .agg(
            documentos=("filename", "size"),
            sucessos=("status", lambda values: int((values == "ok").sum())),
            erros=("status", lambda values: int((values == "error").sum())),
            paginas=(
                "page_count",
                lambda values: float(pd.to_numeric(values, errors="coerce").sum()),
            ),
            duracao_media_s=("duration_seconds", "mean"),
        )
        .reset_index()
    )

    grouped.insert(0, "worker_count", worker_count)
    pod_summary_rows.extend(grouped.to_dict(orient="records"))

pod_summary_df = pd.DataFrame(pod_summary_rows)
pod_summary_df

# %% [markdown]
# ## 12. Erros encontrados

# %%
error_frames: list[pd.DataFrame] = []

for worker_count, runs_df in benchmark_runs.items():
    errors = runs_df[runs_df["status"] == "error"].copy()

    if errors.empty:
        continue

    errors.insert(0, "worker_count", worker_count)
    error_frames.append(errors)

if error_frames:
    errors_df = pd.concat(error_frames, ignore_index=True)
    display(
        errors_df[
            [
                "worker_count",
                "filename",
                "pod_number",
                "api_url",
                "return_code",
                "error",
                "log_path",
            ]
        ]
    )
else:
    errors_df = pd.DataFrame()
    print("Nenhum erro registrado.")

# %% [markdown]
# ## 13. Caminhos dos relatórios

# %%
print(SUMMARY_CSV_PATH.resolve())
print(SUMMARY_PARQUET_PATH.resolve())
print(OUTPUT_ROOT.resolve())
