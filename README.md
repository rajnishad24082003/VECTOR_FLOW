# VectorFlow

Semantic search API built on **FastAPI**, **Hugging Face sentence-transformers** and **Elasticsearch kNN**, with **stateful sessions** (Redis) that carry query context from one search to the next. Ships as lightweight Docker containers.

```
             ┌────────────────────────── api (FastAPI, uvicorn) ───────────────────────────┐
 POST /search│ embed query ──► blend with session context ──► kNN search ──► update session│
             │ (MiniLM, LRU cache,      (Redis)                (Elasticsearch   (Redis)     │
             │  micro-batched)                                  int8 HNSW)                 │
             └─────────────────────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
docker compose up -d --build            # elasticsearch + redis + api on :8000
curl localhost:8000/health

python -m venv .venv && .venv/bin/pip install httpx
.venv/bin/python scripts/ingest.py --jsonl data/sample_docs.jsonl
```

Interactive docs: http://localhost:8000/docs

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents` | Embed and index up to 1000 docs `{id?, title?, text, metadata?}` |
| `DELETE` | `/documents/{id}` | Remove a document |
| `POST` | `/search` | Semantic search (optionally within a session) |
| `POST` | `/sessions` | Start a session |
| `GET` | `/sessions/{id}` | Session history, seen-count |
| `DELETE` | `/sessions/{id}` | End a session |
| `GET` | `/health` | ES / Redis status, doc count |

```bash
curl -s localhost:8000/search -H 'content-type: application/json' -d '{
  "query": "how do I protect my money from rising prices",
  "k": 5,
  "filters": {"category": "finance"}
}'
```

Every response carries `timings` (`embed_ms`, `search_ms`, `total_ms`) and an `X-Response-Time-Ms` header.

### Sessions: continuous query context

```bash
SID=$(curl -s -XPOST localhost:8000/sessions | jq -r .id)
curl ... -d "{\"query\": \"rockets and moon landings\", \"session_id\": \"$SID\"}"
curl ... -d "{\"query\": \"what are the latest missions\", \"session_id\": \"$SID\", \"exclude_seen\": true}"
```

Each session keeps:

- a **context vector**: an exponentially decaying average of past query embeddings (`VF_SESSION_DECAY`). New queries are blended with it (`VF_SESSION_CONTEXT_WEIGHT`), so a vague follow-up stays on the topic the user has been exploring. Set `"use_context": false` to opt out per query.
- the **IDs already shown**, so `"exclude_seen": true` pages through fresh results.
- the recent **query history**.

Sessions are JSON blobs in Redis with a sliding TTL (`VF_SESSION_TTL_SECONDS`, default 30 min). That keeps the API workers stateless, so any number can run behind a load balancer.

## Performance

Measured on a 12-core laptop with a normal desktop workload alongside, using 20k AG News articles (384-dim MiniLM vectors). Queries were unique, so the embedding cache did not help:

```
.venv/bin/python scripts/ingest.py --hf-dataset fancyzhx/ag_news --limit 20000   # needs: pip install datasets
.venv/bin/python scripts/benchmark.py --requests 1000 --concurrency 8
```

| concurrency | throughput | client p50 | client p95 | client p99 | ES search p50 |
|---|---|---|---|---|---|
| 1  | 50 req/s  | 19 ms  | 25 ms  | 27 ms  | 8 ms  |
| 8  | 125 req/s | 63 ms  | 78 ms  | 87 ms  | 9 ms  |
| 16 | 148 req/s | 106 ms | 142 ms | 161 ms | 10 ms |

Elasticsearch stays around 10 ms. Under load, CPU embedding dominates. What keeps it fast:

- **int8-quantised HNSW** (`int8_hnsw`): about 4× less vector memory than float32 and faster kNN.
- **Query embedding LRU cache**: repeated queries skip the model (about 1 ms instead of about 8 ms).
- **Micro-batching**: concurrent queries in a worker share one forward pass instead of queueing for one pass each.
- **No CPU oversubscription**: `WEB_CONCURRENCY × OMP_NUM_THREADS` ≤ cores (defaults 2 × 4). Oversubscription was the biggest source of tail latency in testing: p99 at concurrency 8 was 173 ms before this tuning.
- Model weights are baked into the image and the model is warmed up on startup, so there is no cold first request.

To go beyond about 150 req/s, add API replicas, or set `VF_EMBEDDING_DEVICE=cuda` on a GPU host.

## Configuration

Every setting lives in [app/config.py](app/config.py) and can be overridden with a `VF_` env var. The most useful ones:

| Variable | Default | |
|---|---|---|
| `VF_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Any sentence-transformers model. Also pass it as a build arg so it's baked in: `docker compose build --build-arg VF_EMBEDDING_MODEL=...` |
| `VF_QUERY_PREFIX` / `VF_DOCUMENT_PREFIX` | empty | For e5/bge-style models (`"query: "`, `"passage: "`) |
| `VF_NUM_CANDIDATES_FACTOR` | `10` | HNSW candidates = k × factor (recall vs speed) |
| `VF_SESSION_CONTEXT_WEIGHT` | `0.3` | 0 = sessions don't steer queries |
| `VF_SESSION_DECAY` | `0.6` | How long old context lingers |
| `VF_REDIS_URL` | `redis://localhost:6379/0` | Empty = in-process sessions (single worker only) |

Changing to a model with a different dimension needs a new index (`VF_ES_INDEX`). The API refuses to start against a mismatched index.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Tests use a hashing fake embedder and an in-memory vector store, so they need neither torch nor Elasticsearch.

```
app/
  main.py        app factory + lifespan (builds embedder, ES store, session store)
  api.py         routes
  embeddings.py  HF embedder: LRU cache, micro-batching
  store.py       Elasticsearch index mapping, bulk indexing, filtered kNN
  sessions.py    session model, context blending, Redis / in-memory stores
  schemas.py     request/response models
scripts/         ingest.py (JSONL or HF datasets), benchmark.py
```

## Deploy to a single VM (e.g. Oracle Cloud Always Free)

[deploy/oracle/](deploy/oracle/) adds Caddy (automatic HTTPS) in front of the API and restarts everything on reboot. Searching and sessions are public. Indexing and deleting documents return 403 through Caddy and only work from the VM itself on `127.0.0.1:8000`.

```bash
# On the VM, with Docker installed and ports 80/443 open (cloud firewall + host iptables):
cat > .env <<EOF
SITE_ADDRESS=<ip-with-dashes>.sslip.io   # or your own domain
ES_HEAP=512m
WEB_CONCURRENCY=1                       # keep WEB_CONCURRENCY * OMP_NUM_THREADS <= cores
OMP_NUM_THREADS=1
EOF
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.prod.yml up -d --build
python3 scripts/ingest.py --jsonl data/sample_docs.jsonl --api http://127.0.0.1:8000
```

On a 1 OCPU / 6 GB Ampere A1 instance the stack uses about 1.5 GB of RAM, and warm searches take 35–50 ms.

## Deploy to Hugging Face Spaces (needs PRO)

Docker Spaces need a paid PRO plan for accounts created since mid-2026.

[deploy/hf/](deploy/hf/) packages everything into one container for a free CPU Docker Space (2 vCPU, 16 GB): Elasticsearch bound to localhost with a 512 MB heap, the API on port 7860, and in-memory sessions instead of Redis. Space storage is ephemeral, so the sample docs are re-ingested on every boot.

```bash
# Create a Docker Space at https://huggingface.co/new-space, then:
git clone https://huggingface.co/spaces/<user>/vectorflow ../vectorflow-space
deploy/hf/build_space.sh ../vectorflow-space
cd ../vectorflow-space && git add -A && git commit -m "Deploy VectorFlow" && git push
```

The Space opens on `/docs`. It's ready about 30 s after the container starts and uses about 1.4 GB of RAM. Free Spaces sleep after 48 h without traffic. The next visit wakes them, which takes a few minutes.

### Notes

- `docker-compose.yml` turns off ES's disk-watermark check (`cluster.routing.allocation.disk.threshold_enabled=false`) so it works on nearly full dev disks. Remove it in production.
- ES security is disabled for local use. In production, enable it and set `VF_ES_URL` to https and `VF_ES_API_KEY`.
- Two concurrent searches on the *same* session are last-write-wins for the session update.
