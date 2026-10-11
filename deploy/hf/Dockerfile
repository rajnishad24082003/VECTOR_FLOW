# Single-container image for a Hugging Face Docker Space: Elasticsearch (localhost only) + the API on :7860.
# Build context is the assembled Space repo, see build_space.sh.
FROM docker.elastic.co/elasticsearch/elasticsearch:8.15.3 AS es

# Everything up to the model download matches the main Dockerfile, so local builds reuse its cached layers.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# CPU-only torch keeps the image ~1.5GB smaller than the default CUDA build.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the model into the image so containers start fast and work offline.
ARG VF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV VF_EMBEDDING_MODEL=${VF_EMBEDDING_MODEL}
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['VF_EMBEDDING_MODEL'])"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# For the startup seed (scripts/ingest.py).
RUN pip install "httpx>=0.27"

# The ES distribution ships its own JDK, so it runs as-is on this base image.
COPY --from=es --chown=1000:1000 /usr/share/elasticsearch /usr/share/elasticsearch
COPY --chown=1000:1000 elasticsearch.yml /usr/share/elasticsearch/config/elasticsearch.yml

COPY app ./app
COPY scripts/ingest.py ./scripts/
COPY data/sample_docs.jsonl ./data/
COPY start.sh ./

# Spaces run the container as uid 1000.
RUN useradd --uid 1000 --create-home vf && chown -R vf /opt/hf-cache
USER vf

# Free CPU Spaces have 2 vCPUs: one worker (also required by in-memory sessions) using both cores.
# An empty VF_REDIS_URL switches to in-process sessions, so no Redis is needed.
ENV ES_JAVA_OPTS="-Xms512m -Xmx512m" \
    VF_ES_URL=http://127.0.0.1:9200 \
    VF_REDIS_URL= \
    VF_ES_STARTUP_RETRIES=120 \
    WEB_CONCURRENCY=1 \
    OMP_NUM_THREADS=2

EXPOSE 7860
CMD ["bash", "start.sh"]
