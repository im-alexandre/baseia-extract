# syntax=docker/dockerfile:1.7

FROM vllm/vllm-openai:v0.21.0

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fontconfig \
        fonts-noto-core \
        fonts-noto-cjk \
        libgl1 \
    && fc-cache -f \
    && command -v uv >/dev/null \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/*

COPY --chmod=0755 start.sh /usr/local/bin/start-mineru

EXPOSE 8000
STOPSIGNAL SIGTERM

ENTRYPOINT ["/usr/local/bin/start-mineru"]
