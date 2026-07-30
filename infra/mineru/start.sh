#!/usr/bin/env bash
set -Eeuo pipefail

MINERU_VERSION="${MINERU_VERSION:-3.4.4}"
# A imagem deriva do Python do Ubuntu e expõe no PATH o venv MinerU criado no
# build, com acesso somente-leitura ao PyTorch/CUDA da base. O override
# continua disponível para imagens derivadas.
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASEIA_MODULE_DIR="${BASEIA_MODULE_DIR:-/opt/baseia}"

mkdir -p "${BASEIA_MODULE_DIR}"
for module in \
    catalog_client.py \
    persistent_results.py \
    router_with_persistence.py \
    s3_results.py \
    sitecustomize.py; do
    source_path="${SCRIPT_DIR}/${module}"
    destination_path="${BASEIA_MODULE_DIR}/${module}"
    if [[ -f "${source_path}" && "${source_path}" != "${destination_path}" ]]; then
        install -m 0644 "${source_path}" "${destination_path}"
    elif [[ ! -f "${destination_path}" ]]; then
        printf '[mineru-start] ERROR: módulo BaseIA ausente: %s\n' \
            "${module}" >&2
        exit 1
    fi
done

export MINERU_TOOLS_CONFIG_JSON="${MINERU_TOOLS_CONFIG_JSON:-/opt/mineru/models/mineru.json}"
# Mantenha todos os caches de modelos no volume persistente e deixe overrides
# explícitos sob o namespace MinerU.
export HF_HOME="${MINERU_HF_HOME:-/opt/mineru/models/huggingface}"
export HUGGINGFACE_HUB_CACHE="${MINERU_HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
export MODELSCOPE_CACHE="${MINERU_MODELSCOPE_CACHE:-/opt/mineru/models/modelscope}"
export HF_HUB_ENABLE_HF_TRANSFER=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONUNBUFFERED=1
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${BASEIA_MODULE_DIR}"

printf '[mineru-start] Validando MinerU %s instalado na imagem...\n' \
    "${MINERU_VERSION}"
"${PYTHON_BIN}" -c "from mineru.version import __version__; assert __version__ == '${MINERU_VERSION}', f'a imagem contém MinerU {__version__}, mas MINERU_VERSION=${MINERU_VERSION}; reconstrua a imagem com o build arg correspondente'"
"${PYTHON_BIN}" -c "import mineru.cli.fast_api as api; assert getattr(api, '_baseia_upload_patch', False), 'sitecustomize não aplicou o patch BaseIA'"

mkdir -p \
    "$(dirname "${MINERU_TOOLS_CONFIG_JSON}")" \
    "${HUGGINGFACE_HUB_CACHE}" \
    "${MODELSCOPE_CACHE}"

printf '[mineru-start] Garantindo os modelos pipeline no cache local...\n'
MINERU_MODEL_SOURCE=huggingface \
    mineru-models-download \
    -s huggingface \
    -m pipeline

[[ -s "${MINERU_TOOLS_CONFIG_JSON}" ]] || {
    printf '[mineru-start] ERROR: mineru.json não foi criado.\n' >&2
    exit 1
}

command -v nvidia-smi >/dev/null 2>&1 || {
    printf '[mineru-start] ERROR: nvidia-smi não está disponível.\n' >&2
    exit 1
}
command -v mineru-router >/dev/null 2>&1 || {
    printf '[mineru-start] ERROR: mineru-router não foi instalado.\n' >&2
    exit 1
}

GPU_COUNT="$(
    nvidia-smi --query-gpu=index --format=csv,noheader |
        wc -l |
        tr -d ' '
)"
CPU_COUNT="$(nproc)"
RAM_GIB="$(
    awk '/^MemTotal:/ { printf "%d", $2 / 1024 / 1024 }' /proc/meminfo
)"
VRAM_PER_GPU_MIB="$(
    nvidia-smi \
        --query-gpu=memory.total \
        --format=csv,noheader,nounits |
        awk 'NR == 1 { printf "%d", $1 }'
)"

[[ "${GPU_COUNT}" =~ ^[1-9][0-9]*$ ]] || {
    printf '[mineru-start] ERROR: nenhuma GPU foi detectada.\n' >&2
    exit 1
}

BASEIA_EXPECTED_GPU_COUNT="${GPU_COUNT}" "${PYTHON_BIN}" - <<'PY'
import os
import sys

import torch

expected = int(os.environ["BASEIA_EXPECTED_GPU_COUNT"])
problems = []
if not torch.cuda.is_available():
    problems.append("torch.cuda.is_available()=False")
count = torch.cuda.device_count()
if count != expected:
    problems.append(f"torch GPUs={count}, nvidia-smi GPUs={expected}")
if problems:
    print("[mineru-start] ERROR: preflight CUDA falhou: " + "; ".join(problems), file=sys.stderr)
    raise SystemExit(1)
print(
    "[mineru-start] CUDA preflight OK | "
    f"torch={torch.__version__} | CUDA={torch.version.cuda} | GPUs={count}"
)
PY

CPU_PER_GPU=$((CPU_COUNT / GPU_COUNT))
((CPU_PER_GPU > 0)) || CPU_PER_GPU=1
RAM_PER_GPU_GIB=$((RAM_GIB / GPU_COUNT))
VRAM_PER_GPU_GIB=$((VRAM_PER_GPU_MIB / 1024))

RENDER_THREADS=$((CPU_PER_GPU / 2))
((RENDER_THREADS >= 2)) || RENDER_THREADS=2
((RENDER_THREADS <= 8)) || RENDER_THREADS=8

INTRA_OP_THREADS="${CPU_PER_GPU}"
((INTRA_OP_THREADS >= 4)) || INTRA_OP_THREADS=4
((INTRA_OP_THREADS <= 12)) || INTRA_OP_THREADS=12

# O serviço anuncia um teto alto; o cliente BaseIA controla a pressão real
# por endpoint por meio de `poe extract ... --workers N`.
export MINERU_ROUTER_LOCAL_GPUS="${MINERU_ROUTER_LOCAL_GPUS:-auto}"
# O /health do router 3.4.4 soma os limites dos workers saudáveis. O default
# acomoda o lote esperado de 120 sem anunciar capacidade ilimitada.
MINERU_ROUTER_AGGREGATE_MAX_CONCURRENT_REQUESTS="${MINERU_ROUTER_MAX_CONCURRENT_REQUESTS:-128}"
[[ "${MINERU_ROUTER_AGGREGATE_MAX_CONCURRENT_REQUESTS}" =~ ^[1-9][0-9]*$ ]] || {
    printf '[mineru-start] ERROR: MINERU_ROUTER_MAX_CONCURRENT_REQUESTS inválido.\n' >&2
    exit 1
}
MINERU_API_MAX_CONCURRENT_REQUESTS=$((MINERU_ROUTER_AGGREGATE_MAX_CONCURRENT_REQUESTS / GPU_COUNT))
((MINERU_API_MAX_CONCURRENT_REQUESTS > 0)) || {
    printf '[mineru-start] ERROR: GPUs demais para o teto agregado do router.\n' >&2
    exit 1
}
export MINERU_API_MAX_CONCURRENT_REQUESTS
export MINERU_PROCESSING_WINDOW_SIZE="${MINERU_PROCESSING_WINDOW_SIZE:-64}"
export MINERU_PDF_RENDER_THREADS="${MINERU_PDF_RENDER_THREADS:-${RENDER_THREADS}}"
export MINERU_INTRA_OP_NUM_THREADS="${MINERU_INTRA_OP_NUM_THREADS:-${INTRA_OP_THREADS}}"
export MINERU_INTER_OP_NUM_THREADS="${MINERU_INTER_OP_NUM_THREADS:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-${CPU_PER_GPU}}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-${CPU_PER_GPU}}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-${CPU_PER_GPU}}"
# MinerU 3.4.4 trata 0 como retenção desativada: não inicia o cleanup e
# cleanup_expired_tasks retorna sem remover outputs. Isso impede apagar antes
# da cópia atômica do reconciliador.
export MINERU_API_TASK_RETENTION_SECONDS="${MINERU_API_TASK_RETENTION_SECONDS:-0}"
export MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS="${MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS:-60}"
# /workspace é o Network Volume e contém exclusivamente resultados publicados.
# Cada worker e seus intermediários ficam no disco local do container.
export MINERU_LOCAL_WORK_ROOT="${MINERU_LOCAL_WORK_ROOT:-/tmp/mineru-active}"
export MINERU_API_OUTPUT_ROOT="${MINERU_API_OUTPUT_ROOT:-${MINERU_LOCAL_WORK_ROOT}/api-output}"
export MINERU_PERSISTENT_RESULTS_ROOT="${MINERU_PERSISTENT_RESULTS_ROOT:-/workspace/results}"
export MINERU_RESULT_STORE="${MINERU_RESULT_STORE:-filesystem}"
export MINERU_MAX_UNPERSISTED_TASKS="${MINERU_MAX_UNPERSISTED_TASKS:-256}"
export MINERU_MIN_FREE_DISK_GIB="${MINERU_MIN_FREE_DISK_GIB:-10}"
export MINERU_MIN_FREE_DISK_PERCENT="${MINERU_MIN_FREE_DISK_PERCENT:-10}"
export MINERU_MODEL_SOURCE=local

if [[ -n "${BASEIA_CATALOG_API_URL:-}" && "${MINERU_RESULT_STORE}" != "s3" ]]; then
    printf '%s\n' \
        '[mineru-start] ERROR: catálogo exige MINERU_RESULT_STORE=s3.' \
        'O catálogo nunca pode concluir uma task sem artefatos duráveis no S3.' >&2
    exit 1
fi

[[ "${MINERU_API_OUTPUT_ROOT}" != /workspace && "${MINERU_API_OUTPUT_ROOT}" != /workspace/* ]] || {
    printf '[mineru-start] ERROR: MINERU_API_OUTPUT_ROOT não pode ficar sob /workspace.\n' >&2
    exit 1
}
[[ "${MINERU_PERSISTENT_RESULTS_ROOT}" == "/workspace/results" ]] || {
    printf '[mineru-start] ERROR: MINERU_PERSISTENT_RESULTS_ROOT deve ser /workspace/results.\n' >&2
    exit 1
}
mkdir -p "${MINERU_LOCAL_WORK_ROOT}" "${MINERU_API_OUTPUT_ROOT}" "/tmp/mineru-uploads"
if [[ "${MINERU_RESULT_STORE}" == "s3" ]]; then
    "${PYTHON_BIN}" -c "import s3_results; s3_results.ensure_bucket()"
fi
ulimit -n 65535 2>/dev/null || true

GPU_SUMMARY="$(
    nvidia-smi \
        --query-gpu=index,name,memory.total \
        --format=csv,noheader,nounits |
        sed 's/^/  GPU /; s/, / | /g'
)"

printf '%s\n' \
    "============================================================" \
    " MinerU pipeline startup" \
    " GPUs               : ${GPU_COUNT}" \
    "${GPU_SUMMARY}" \
    " CPU                : ${CPU_COUNT} (${CPU_PER_GPU}/GPU)" \
    " RAM                : ${RAM_GIB} GiB (${RAM_PER_GPU_GIB}/GPU)" \
    " VRAM               : ${VRAM_PER_GPU_GIB} GiB/GPU" \
    " Router API limit   : ${MINERU_ROUTER_AGGREGATE_MAX_CONCURRENT_REQUESTS} agregado (${MINERU_API_MAX_CONCURRENT_REQUESTS}/GPU)" \
    " Processing window  : ${MINERU_PROCESSING_WINDOW_SIZE}" \
    " PDF render threads : ${MINERU_PDF_RENDER_THREADS}/GPU" \
    " Torch threads      : ${MINERU_INTRA_OP_NUM_THREADS}/${MINERU_INTER_OP_NUM_THREADS}" \
    " Models             : ${MINERU_TOOLS_CONFIG_JSON}" \
    " Local work root    : ${MINERU_LOCAL_WORK_ROOT}" \
    " Results            : ${MINERU_PERSISTENT_RESULTS_ROOT}/tasks/<router-task-id>" \
    " Result store       : ${MINERU_RESULT_STORE}" \
    " Backlog limit      : ${MINERU_MAX_UNPERSISTED_TASKS} tasks" \
    " Min free disk      : ${MINERU_MIN_FREE_DISK_GIB} GiB / ${MINERU_MIN_FREE_DISK_PERCENT}%" \
    " Retention          : disabled until persistence is durable" \
    " Listen             : ${MINERU_HOST:-0.0.0.0}:${PORT:-8000}" \
    "============================================================"

"${PYTHON_BIN}" -m persistent_results --watch &
PERSISTENCE_PID=$!
"${PYTHON_BIN}" -m router_with_persistence \
    --host "${MINERU_HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --local-gpus "${MINERU_ROUTER_LOCAL_GPUS}" \
    "$@" &
ROUTER_PID=$!

cleanup_children() {
    trap - EXIT INT TERM
    kill -TERM "${ROUTER_PID}" "${PERSISTENCE_PID}" 2>/dev/null || true
    wait "${ROUTER_PID}" 2>/dev/null || true
    wait "${PERSISTENCE_PID}" 2>/dev/null || true
}

trap 'cleanup_children; exit 143' INT TERM

set +e
wait -n "${ROUTER_PID}" "${PERSISTENCE_PID}"
CHILD_STATUS=$?
set -e

if ! kill -0 "${ROUTER_PID}" 2>/dev/null; then
    printf '[mineru-start] router encerrou; derrubando reconciliador.\n' >&2
    cleanup_children
else
    printf '[mineru-start] reconciliador encerrou; router continua ativo.\n' >&2
    set +e
    wait "${ROUTER_PID}"
    CHILD_STATUS=$?
    set -e
    cleanup_children
fi

# Nenhum dos dois processos tem encerramento normal enquanto o pod está ativo.
(( CHILD_STATUS != 0 )) || CHILD_STATUS=1
exit "${CHILD_STATUS}"
