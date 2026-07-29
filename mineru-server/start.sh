#!/usr/bin/env bash
set -Eeuo pipefail

MINERU_VERSION="${MINERU_VERSION:-3.4.4}"
# A imagem RunPod instala os pacotes em /usr/local/bin/python (3.12); o
# /usr/bin/python3 pode ser um 3.10 sem MinerU. Preserve essa coerência.
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3)}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASEIA_MODULE_DIR="${BASEIA_MODULE_DIR:-/opt/baseia}"

mkdir -p "${BASEIA_MODULE_DIR}"
for module in persistent_results.py router_with_persistence.py sitecustomize.py; do
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
export HF_HOME="${HF_HOME:-/opt/mineru/models/huggingface}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-/opt/mineru/models/modelscope}"
export HF_HUB_ENABLE_HF_TRANSFER=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONUNBUFFERED=1
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${BASEIA_MODULE_DIR}"

printf '[mineru-start] Instalando pip, uv, MinerU %s e hf_transfer...\n' \
    "${MINERU_VERSION}"
"${PYTHON_BIN}" -m pip install --upgrade pip uv
# O módulo de persistência usa Tenacity e é importado por sitecustomize. Faça
# seu bootstrap sem PYTHONPATH antes de qualquer comando Python que carregue o
# patch do servidor.
PYTHONPATH="" "${PYTHON_BIN}" -m uv pip install --system "tenacity>=9,<10"
# Preserve o PyTorch/CUDA já compatível com o template; não force reinstalação
# nem uma variante CUDA específica.
"${PYTHON_BIN}" -m uv pip install --system \
    "mineru[pipeline]==${MINERU_VERSION}" \
    hf_transfer
"${PYTHON_BIN}" -c "import mineru; from mineru.version import __version__; assert __version__ == '${MINERU_VERSION}', __version__"
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
# por pod por meio de `poe ingest POD_ID --workers N`.
export MINERU_ROUTER_LOCAL_GPUS="${MINERU_ROUTER_LOCAL_GPUS:-auto}"
# O /health do router 3.4.4 soma os limites dos workers saudáveis. Distribua
# o teto do pod entre GPUs para anunciar no máximo 1024 agregado.
MINERU_ROUTER_AGGREGATE_MAX_CONCURRENT_REQUESTS=1024
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
export MINERU_MODEL_SOURCE=local

[[ "${MINERU_API_OUTPUT_ROOT}" != /workspace && "${MINERU_API_OUTPUT_ROOT}" != /workspace/* ]] || {
    printf '[mineru-start] ERROR: MINERU_API_OUTPUT_ROOT não pode ficar sob /workspace.\n' >&2
    exit 1
}
[[ "${MINERU_PERSISTENT_RESULTS_ROOT}" == "/workspace/results" ]] || {
    printf '[mineru-start] ERROR: MINERU_PERSISTENT_RESULTS_ROOT deve ser /workspace/results.\n' >&2
    exit 1
}
mkdir -p "${MINERU_LOCAL_WORK_ROOT}" "${MINERU_API_OUTPUT_ROOT}" "/tmp/mineru-uploads"
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
