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

COPY app ./app

RUN useradd --uid 1000 --create-home vf && chown -R vf /opt/hf-cache
USER vf

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

# Worker count comes from WEB_CONCURRENCY (uvicorn default: 1).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
