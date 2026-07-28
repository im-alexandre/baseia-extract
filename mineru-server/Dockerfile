FROM vllm/vllm-openai:v0.21.0

USER root

RUN uv venv /opt/mineru-venv \
  --python "$(command -v python3)" \
  --system-site-packages \
  --seed \
  && /opt/mineru-venv/bin/python -m pip install \
  --no-cache-dir \
  "mineru[core]==3.4.4"

COPY start.sh /usr/local/bin/start-mineru
RUN chmod 0755 /usr/local/bin/start-mineru

ENTRYPOINT ["/usr/local/bin/start-mineru"]
CMD []
