#!/usr/bin/env bash
set -Eeuo pipefail

RUNTIME_ROOT="/workspace/mineru-runtime"
VENV="/workspace/.venv"
MODELS_ROOT="/workspace/mineru-models"

MINERU_VERSION="${MINERU_VERSION:-3.4.0}"
PORT="${PORT:-8000}"

VENV_READY="${VENV}/.mineru-${MINERU_VERSION}-ready"
VENV_LOCK="/workspace/.mineru-venv-lock"

MODELS_READY="${MODELS_ROOT}/.models-ready"
MODELS_LOCK="/workspace/.mineru-models-lock"

export HF_HOME="${MODELS_ROOT}/huggingface"
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export MODELSCOPE_CACHE="${MODELS_ROOT}/modelscope"
export MINERU_TOOLS_CONFIG_JSON="${MODELS_ROOT}/mineru.json"
export MINERU_API_OUTPUT_ROOT="${MODELS_ROOT}/output"
export MINERU_API_MAX_CONCURRENT_REQUESTS="${
    MINERU_API_MAX_CONCURRENT_REQUESTS:-1
}"

mkdir -p \
    "${RUNTIME_ROOT}" \
    "${MODELS_ROOT}" \
    "${HF_HOME}" \
    "${HUGGINGFACE_HUB_CACHE}" \
    "${MODELSCOPE_CACHE}" \
    "${MINERU_API_OUTPUT_ROOT}"

wait_for_file() {
    local file="$1"
    local lock="$2"
    local timeout="${3:-7200}"
    local deadline

    deadline=$(($(date +%s) + timeout))

    while [[ ! -f "${file}" ]]; do
        if [[ ! -d "${lock}" ]]; then
            return 1
        fi

        if (( $(date +%s) >= deadline )); then
            echo "Timeout aguardando ${file}" >&2
            exit 1
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
        "mineru[core]==${MINERU_VERSION}"

    touch "${VENV_READY}"
}

if [[ ! -x "${VENV}/bin/mineru-api" || ! -f "${VENV_READY}" ]]; then
    if mkdir "${VENV_LOCK}" 2>/dev/null; then
        trap 'rm -rf "${VENV_LOCK}"' EXIT INT TERM

        install_runtime

        rm -rf "${VENV_LOCK}"
        trap - EXIT INT TERM
    else
        echo "Outro Pod está preparando o ambiente Python..."
        wait_for_file "${VENV_READY}" "${VENV_LOCK}"
    fi
fi

download_models() {
    rm -f "${MODELS_READY}"

    MINERU_MODEL_SOURCE=huggingface \
        "${VENV}/bin/mineru-models-download" \
        -s huggingface \
        -m all

    [[ -s "${MINERU_TOOLS_CONFIG_JSON}" ]] || {
        echo "mineru.json não foi criado." >&2
        exit 1
    }

    touch "${MODELS_READY}"
}

if [[ ! -f "${MODELS_READY}" ]]; then
    if mkdir "${MODELS_LOCK}" 2>/dev/null; then
        trap 'rm -rf "${MODELS_LOCK}"' EXIT INT TERM

        download_models

        rm -rf "${MODELS_LOCK}"
        trap - EXIT INT TERM
    else
        echo "Outro Pod está baixando os modelos..."
        wait_for_file "${MODELS_READY}" "${MODELS_LOCK}"
    fi
fi

export MINERU_MODEL_SOURCE=local

exec "${VENV}/bin/mineru-api" \
    --host 0.0.0.0 \
    --port "${PORT}"
