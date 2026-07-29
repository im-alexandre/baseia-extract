FROM runpod/base:1.1.0-cuda1281-ubuntu2204

ENV DEBIAN_FRONTEND=noninteractive

# Dependências de renderização e fontes necessárias ao MinerU instalado no boot.
RUN apt-get update \
  && apt-get install --yes --no-install-recommends \
    fontconfig \
    fonts-noto-cjk \
    fonts-noto-core \
    libgl1 \
  && fc-cache -f \
  && rm -rf /var/lib/apt/lists/*

# O Network Volume contém exclusivamente os resultados persistidos.
WORKDIR /workspace/results

COPY --chmod=0755 start.sh /usr/local/bin/start-mineru-api
COPY persistent_results.py router_with_persistence.py sitecustomize.py /opt/baseia/

ENTRYPOINT ["/usr/local/bin/start-mineru-api"]
