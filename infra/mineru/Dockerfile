ARG PYTORCH_IMAGE=pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime@sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be
FROM ${PYTORCH_IMAGE}

ARG MINERU_VERSION=3.4.4
ENV DEBIAN_FRONTEND=noninteractive \
    MINERU_VERSION=${MINERU_VERSION} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/mineru/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Dependências nativas de renderização, OpenCV, Torch e fontes.
RUN apt-get update \
  && apt-get install --yes --no-install-recommends \
    fontconfig \
    fonts-noto-cjk \
    fonts-noto-core \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    python3-venv \
  && fc-cache -f \
  && rm -rf /var/lib/apt/lists/*

# A base oficial já contém Python, CUDA, cuDNN, Torch e Torchvision. Instale o
# MinerU em um venv que reutiliza essa pilha somente-leitura; o boot não
# resolve nem altera dependências. O pip respeita os pacotes visíveis por
# --system-site-packages; os pins impedem trocar a variante CUDA da base.
RUN /usr/bin/python -m venv --system-site-packages "${VIRTUAL_ENV}" \
  && python -m pip install --no-cache-dir \
    "anyio>=4.11,<5" \
    "boto3>=1.42,<2" \
    "click>=8,<8.3" \
    "tenacity>=9,<10" \
    "mineru[pipeline]==${MINERU_VERSION}" \
    "hf_transfer==0.1.9" \
    "torch==2.11.0" \
    "torchvision==0.26.0" \
  && python -c "import cv2, pypdfium2, torch, torchvision; from mineru.version import __version__; assert __version__ == '${MINERU_VERSION}', __version__; assert torch.__version__.split('+', 1)[0] == '2.11.0', torch.__version__; assert torch.version.cuda == '12.8', torch.version.cuda" \
  && command -v mineru-router >/dev/null

# O volume contém exclusivamente os resultados persistidos.
WORKDIR /workspace/results

COPY --chmod=0755 start.sh /usr/local/bin/start-mineru-api
COPY \
  catalog_client.py \
  persistent_results.py \
  router_with_persistence.py \
  s3_results.py \
  sitecustomize.py \
  /opt/baseia/

ENTRYPOINT ["/usr/local/bin/start-mineru-api"]
