#!/usr/bin/env bash
set -Eeuo pipefail

VENV="${MINERU_VENV:-/workspace/.venv}"
MODELS_ROOT="${MINERU_MODELS_ROOT:-/workspace/mineru-models}"
API_OUTPUT_ROOT="${MINERU_API_OUTPUT_ROOT:-/tmp/mineru-api-output}"

MINERU_VERSION="${MINERU_VERSION:-3.4.0}"
PORT="${PORT:-8000}"
MINERU_API_MAX_CONCURRENT_REQUESTS="${MINERU_API_MAX_CONCURRENT_REQUESTS:-8}"
MINERU_API_ENABLE_FASTAPI_DOCS="${MINERU_API_ENABLE_FASTAPI_DOCS:-true}"
PREPARE_TIMEOUT_SECONDS="${MINERU_PREPARE_TIMEOUT_SECONDS:-7200}"

VENV_READY="${VENV}/.mineru-${MINERU_VERSION}-pipeline-ready"
VENV_LOCK="/workspace/.mineru-venv-lock"
MODELS_READY="${MODELS_ROOT}/.mineru-${MINERU_VERSION}-pipeline-models-ready"
MODELS_LOCK="/workspace/.mineru-models-lock"

export HF_HOME="${MODELS_ROOT}/huggingface"
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export MODELSCOPE_CACHE="${MODELS_ROOT}/modelscope"
export MINERU_TOOLS_CONFIG_JSON="${MODELS_ROOT}/mineru.json"
export MINERU_API_OUTPUT_ROOT="${API_OUTPUT_ROOT}"
export MINERU_API_MAX_CONCURRENT_REQUESTS
export MINERU_API_ENABLE_FASTAPI_DOCS
export PYTHONUNBUFFERED=1

mkdir -p \
    "${MODELS_ROOT}" \
    "${HF_HOME}" \
    "${HUGGINGFACE_HUB_CACHE}" \
    "${MODELSCOPE_CACHE}" \
    "${MINERU_API_OUTPUT_ROOT}"

ACTIVE_LOCK=""

cleanup_lock() {
    if [[ -n "${ACTIVE_LOCK}" ]]; then
        rm -rf "${ACTIVE_LOCK}"
    fi
}

trap cleanup_lock EXIT INT TERM

wait_for_owner() {
    local marker="$1"
    local lock="$2"
    local description="$3"
    local deadline

    deadline=$(($(date +%s) + PREPARE_TIMEOUT_SECONDS))

    while [[ ! -f "${marker}" && -d "${lock}" ]]; do
        if (( $(date +%s) >= deadline )); then
            echo "Timeout aguardando ${description}: ${marker}" >&2
            return 1
        fi

        sleep 5
    done
}

install_runtime() {
    rm -rf "${VENV}"

    uv venv \
        --python "$(command -v python3)" \
        --system-site-packages \
        --seed \
        "${VENV}"

    "${VENV}/bin/python" -m pip install \
        --no-cache-dir \
        --upgrade \
        "mineru[pipeline]==${MINERU_VERSION}"

    "${VENV}/bin/python" - <<PY
from importlib.metadata import version

actual = version("mineru")
expected = "${MINERU_VERSION}"

if actual != expected:
    raise SystemExit(
        f"MinerU instalado em versão inesperada: {actual} != {expected}"
    )
PY

    [[ -x "${VENV}/bin/mineru-api" ]] || {
        echo "mineru-api não foi instalado em ${VENV}." >&2
        return 1
    }

    touch "${VENV_READY}"
}

ensure_runtime() {
    while [[ ! -x "${VENV}/bin/mineru-api" || ! -f "${VENV_READY}" ]]; do
        if mkdir "${VENV_LOCK}" 2>/dev/null; then
            ACTIVE_LOCK="${VENV_LOCK}"

            if [[ ! -x "${VENV}/bin/mineru-api" || ! -f "${VENV_READY}" ]]; then
                echo "Preparando MinerU ${MINERU_VERSION} em ${VENV}..."
                install_runtime
            fi

            rm -rf "${VENV_LOCK}"
            ACTIVE_LOCK=""
        else
            echo "Outro Pod está preparando o ambiente Python..."
            wait_for_owner \
                "${VENV_READY}" \
                "${VENV_LOCK}" \
                "o ambiente Python"
        fi
    done
}

download_models() {
    rm -f "${MODELS_READY}"

    MINERU_MODEL_SOURCE=huggingface \
        "${VENV}/bin/mineru-models-download" \
        -s huggingface \
        -m pipeline

    [[ -s "${MINERU_TOOLS_CONFIG_JSON}" ]] || {
        echo "mineru.json não foi criado em ${MINERU_TOOLS_CONFIG_JSON}." >&2
        return 1
    }

    touch "${MODELS_READY}"
}

ensure_models() {
    while [[ ! -f "${MODELS_READY}" || ! -s "${MINERU_TOOLS_CONFIG_JSON}" ]]; do
        if mkdir "${MODELS_LOCK}" 2>/dev/null; then
            ACTIVE_LOCK="${MODELS_LOCK}"

            if [[ ! -f "${MODELS_READY}" || ! -s "${MINERU_TOOLS_CONFIG_JSON}" ]]; then
                echo "Preparando modelos pipeline em ${MODELS_ROOT}..."
                download_models
            fi

            rm -rf "${MODELS_LOCK}"
            ACTIVE_LOCK=""
        else
            echo "Outro Pod está baixando os modelos pipeline..."
            wait_for_owner \
                "${MODELS_READY}" \
                "${MODELS_LOCK}" \
                "os modelos pipeline"
        fi
    done
}

ensure_runtime
ensure_models

export MINERU_MODEL_SOURCE=local

if (( $# > 0 )); then
    echo "Ignorando argumentos herdados da imagem/template: $*"
fi

echo "Iniciando MinerU API ${MINERU_VERSION} na porta ${PORT}."
echo "Backend provisionado: pipeline."
echo "Concorrência máxima: ${MINERU_API_MAX_CONCURRENT_REQUESTS}."
echo "Configuração: ${MINERU_TOOLS_CONFIG_JSON}."
echo "Saída temporária: ${MINERU_API_OUTPUT_ROOT}."

exec "${VENV}/bin/mineru-api" \
    --host 0.0.0.0 \
    --port "${PORT}"
