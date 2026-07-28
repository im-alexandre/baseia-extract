# syntax=docker/dockerfile:1.7

FROM vllm/vllm-openai:v0.21.0

ARG MINERU_VERSION=3.4.0

ENV DEBIAN_FRONTEND=noninteractive \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_NO_CACHE_DIR=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  HF_HOME=/workspace/mineru/huggingface \
  HUGGINGFACE_HUB_CACHE=/workspace/mineru/huggingface/hub \
  MODELSCOPE_CACHE=/workspace/mineru/modelscope \
  MINERU_TOOLS_CONFIG_JSON=/workspace/mineru/mineru.json \
  MINERU_MODEL_SOURCE=local \
  MINERU_API_OUTPUT_ROOT=/workspace/mineru/output \
  MINERU_API_MAX_CONCURRENT_REQUESTS=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  fontconfig \
  fonts-noto-core \
  fonts-noto-cjk \
  libgl1 \
  && fc-cache -f \
  && apt-get clean \
  && rm -rf \
  /var/lib/apt/lists/* \
  /root/.cache \
  /tmp/*

RUN python3 -m pip install \
  --no-cache-dir \
  --upgrade \
  "mineru[core]==${MINERU_VERSION}" \
  --break-system-packages \
  && rm -rf \
  /root/.cache \
  /tmp/*

COPY --chmod=0755 start.sh /usr/local/bin/start-mineru

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/start-mineru"]
