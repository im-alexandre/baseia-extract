# Use the official vllm image for gpu with Volta、Turing、Ampere、Ada Lovelace、Hopper、Blackwell architecture (7.0 <= Compute Capability <= 12.1)
# The default base image uses vLLM 0.21.0 with CUDA 13.0. For CUDA 12.9 environments, switch to the commented cu129 image below.
# Compute Capability version query (https://developer.nvidia.com/cuda-gpus)
# support x86_64 architecture and ARM(AArch64) architecture
FROM vllm/vllm-openai:v0.21.0
# FROM vllm/vllm-openai:v0.21.0-cu129

# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
  apt-get install -y \
  fonts-noto-core \
  fonts-noto-cjk \
  fontconfig \
  libgl1 && \
  fc-cache -fv && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Install mineru latest
RUN python3 -m pip install -U 'mineru[core]>=3.4.0' --break-system-packages && \
  python3 -m pip cache purge

COPY start.sh /usr/local/bin/start-mineru
RUN chmod +x /usr/local/bin/start-mineru

ENV HF_HOME=/opt/mineru-models/huggingface
ENV HUGGINGFACE_HUB_CACHE=/opt/mineru-models/huggingface/hub
ENV MODELSCOPE_CACHE=/opt/mineru-models/modelscope
ENV MINERU_TOOLS_CONFIG_JSON=/root/mineru.json
ENV MINERU_MODEL_SOURCE=local
ENV MINERU_API_MAX_CONCURRENT_REQUESTS=1

RUN mkdir -p \
  /opt/mineru-models/huggingface \
  /opt/mineru-models/modelscope

RUN uv pip install --system --upgrade \
  "huggingface_hub[hf_transfer]"

RUN mineru-models-download \
  -s huggingface \
  -m all

COPY start.sh /usr/local/bin/start-mineru
RUN chmod +x /usr/local/bin/start-mineru

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/start-mineru"]
