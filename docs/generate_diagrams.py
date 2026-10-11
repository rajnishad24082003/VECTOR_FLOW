"""Generate docs/VectorFlow-HLD.drawio and docs/VectorFlow-LLD.drawio."""

import html
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(sys.argv[1])

# ----------------------------------------------------------------------------- helpers

COLORS = {
    "api": ("#d5e8d4", "#82b366"),
    "emb": ("#dae8fc", "#6c8ebf"),
    "store": ("#ffe6cc", "#d79b00"),
    "sess": ("#e1d5e7", "#9673a6"),
    "core": ("#f5f5f5", "#666666"),
    "schema": ("#fff2cc", "#d6b656"),
    "script": ("#f8cecc", "#b85450"),
    "ext": ("#ffffff", "#000000"),
    "note": ("#fffbe6", "#b7a33a"),
}


def esc(s: str) -> str:
    return html.escape(s, quote=False)


class Label:
    """Builds an HTML label and estimates its rendered height for a given width."""

    LINE = 13.6

    def __init__(self, width: int, font: int = 11):
        self.parts: list[str] = []
        self.lines = 0.0
        self.cpl = max(10, (width - 24) / (font * 0.56))

    def _count(self, text: str, scale: float = 1.0) -> None:
        self.lines += max(1, math.ceil(len(text) * scale / self.cpl))

    def title(self, t: str, sub: str | None = None):
        self.parts.append(f'<div style="text-align:center"><b><font style="font-size:14px">{esc(t)}</font></b></div>')
        self._count(t, 1.35)
        self.lines += 0.3
        if sub:
            self.parts.append(f'<div style="text-align:center"><i>{esc(sub)}</i></div>')
            self._count(sub)
        return self

    def hr(self):
        self.parts.append("<hr>")
        self.lines += 0.9
        return self

    def section(self, t: str):
        self.parts.append(f'<div style="margin-top:4px"><b><u>{esc(t)}</u></b></div>')
        self._count(t)
        self.lines += 0.3
        return self

    def item(self, sig: str, desc: str = ""):
        body = f'<b><font color="#1a3d7c" face="Courier New">{esc(sig)}</font></b>'
        self._count(sig, 1.12)
        for line in [d for d in desc.split("\n") if d] if desc else []:
            body += f"<br>{esc(line)}"
            self._count(line)
        self.parts.append(f'<div style="margin-bottom:5px">{body}</div>')
        self.lines += 0.35
        return self

    def text(self, t: str, bold: bool = False):
        for line in t.split("\n"):
            stripped = line.lstrip(" ")
            content = "&nbsp;" * (len(line) - len(stripped)) + esc(stripped)
            content = f"<b>{content}</b>" if bold else content
            self.parts.append(f"<div>{content}</div>")
            self._count(line)
        return self

    def bullets(self, items: list[str]):
        for it in items:
            self.parts.append(f"<div>&bull; {esc(it)}</div>")
            self._count("  " + it)
        return self

    def html(self) -> str:
        return "".join(self.parts)

    def height(self) -> int:
        return int(self.lines * self.LINE * 1.06 + 22)


def box_style(kind: str, extra: str = "") -> str:
    fill, stroke = COLORS[kind]
    return (
        "rounded=1;arcSize=2;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=10;"
        f"spacingRight=10;spacingTop=6;fontSize=11;fillColor={fill};strokeColor={stroke};{extra}"
    )


class Page:
    def __init__(self, name: str):
        self.name = name
        self.cells: list[ET.Element] = []
        self.n = 0
        self.max_x = self.max_y = 0

    def _id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def vertex(self, x, y, w, h, value, style, parent="1") -> str:
        cid = self._id()
        c = ET.Element("mxCell", id=cid, value=value, style=style, vertex="1", parent=parent)
        ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h), **{"as": "geometry"})
        self.cells.append(c)
        self.max_x, self.max_y = max(self.max_x, x + w), max(self.max_y, y + h)
        return cid

    def box(self, x, y, w, label: Label, kind="core", extra="", min_h=0) -> tuple[str, int]:
        h = max(min_h, label.height())
        return self.vertex(x, y, w, h, label.html(), box_style(kind, extra)), h

    def simple(self, x, y, w, h, text, kind="core", extra="") -> str:
        fill, stroke = COLORS[kind]
        style = f"rounded=1;whiteSpace=wrap;html=1;fontSize=11;fillColor={fill};strokeColor={stroke};{extra}"
        return self.vertex(x, y, w, h, text, style)

    def heading(self, x, y, w, text, size=22):
        return self.vertex(
            x, y, w, 40, f"<b>{esc(text)}</b>",
            f"text;html=1;fontSize={size};align=left;verticalAlign=middle;strokeColor=none;fillColor=none;",
        )

    def edge(self, src, tgt, label="", style="", exit_=None, entry=None, points=None) -> str:
        cid = self._id()
        st = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=10;endArrow=block;endFill=1;"
            "labelBackgroundColor=#ffffff;" + style
        )
        if exit_:
            st += f"exitX={exit_[0]};exitY={exit_[1]};exitDx=0;exitDy=0;"
        if entry:
            st += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        c = ET.Element("mxCell", id=cid, value=label, style=st, edge="1", parent="1", source=src, target=tgt)
        g = ET.SubElement(c, "mxGeometry", relative="1", **{"as": "geometry"})
        if points:
            arr = ET.SubElement(g, "Array", **{"as": "points"})
            for px, py in points:
                ET.SubElement(arr, "mxPoint", x=str(px), y=str(py))
        self.cells.append(c)
        return cid

    def line(self, x1, y1, x2, y2, label="", style="") -> str:
        """Free-floating edge between two points (used for sequence diagram messages)."""
        cid = self._id()
        st = "html=1;fontSize=10;endArrow=block;endFill=1;verticalAlign=bottom;labelBackgroundColor=none;" + style
        c = ET.Element("mxCell", id=cid, value=label, style=st, edge="1", parent="1")
        g = ET.SubElement(c, "mxGeometry", width="50", height="50", relative="1", **{"as": "geometry"})
        ET.SubElement(g, "mxPoint", x=str(x1), y=str(y1), **{"as": "sourcePoint"})
        ET.SubElement(g, "mxPoint", x=str(x2), y=str(y2), **{"as": "targetPoint"})
        self.cells.append(c)
        return cid

    def element(self) -> ET.Element:
        d = ET.Element("diagram", name=self.name, id=self.name.lower().replace(" ", "-")[:40])
        m = ET.SubElement(
            d, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1", tooltips="1",
            connect="1", arrows="1", fold="1", page="1", pageScale="1",
            pageWidth=str(int(self.max_x + 60)), pageHeight=str(int(self.max_y + 60)), math="0", shadow="0",
        )
        root = ET.SubElement(m, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        root.extend(self.cells)
        return d


def write(path: Path, pages: list[Page]) -> None:
    f = ET.Element("mxfile", host="app.diagrams.net", type="device")
    for p in pages:
        f.append(p.element())
    ET.indent(f)
    path.write_text(ET.tostring(f, encoding="unicode"), encoding="utf-8")
    print(f"wrote {path} ({len(pages)} pages)")


def column(page: Page, x: int, y: int, w: int, specs, gap=24) -> dict[str, str]:
    """Stack boxes vertically. specs: list of (key, Label, kind)."""
    ids = {}
    for key, label, kind in specs:
        cid, h = page.box(x, y, w, label, kind)
        ids[key] = cid
        y += h + gap
    return ids


def flow(page: Page, x, y, steps, w=200, h=110, gap=46, kind="core", wrap=None) -> list[str]:
    """Horizontal (optionally wrapping) chain of step boxes joined by arrows."""
    ids = []
    cx, cy = x, y
    for i, (title, desc) in enumerate(steps):
        if wrap and i and i % wrap == 0:
            cx, cy = x, cy + h + 60
        label = f'<b>{i + 1}. {esc(title)}</b><br><font style="font-size:10px">{esc(desc)}</font>'
        ids.append(page.simple(cx, cy, w, h, label, kind, "verticalAlign=top;spacingTop=4;"))
        cx += w + gap
    for a, b in zip(ids, ids[1:]):
        page.edge(a, b)
    return ids


# ============================================================================= HLD

def hld() -> list[Page]:
    pages = []

    # ---------------------------------------------------------------- 1. architecture
    p = Page("1. System Architecture")
    p.heading(40, 20, 1600, "VectorFlow — High Level Design: System Architecture")
    p.vertex(40, 60, 1600, 24,
             "Semantic Search API  |  Python 3.12 · FastAPI · Hugging Face sentence-transformers · Elasticsearch 8.15 · Redis 7 · Docker Compose",
             "text;html=1;fontSize=12;align=left;fontColor=#555555;strokeColor=none;fillColor=none;")

    client = p.simple(40, 170, 220, 100,
                      "<b>API Clients</b><br>Web/mobile frontends, backend services, curl, Swagger UI (/docs)",
                      "ext", "shape=actor;verticalLabelPosition=bottom;verticalAlign=top;" if False else "")
    ops_l = Label(220).title("Operator Scripts", "run on host, talk HTTP").hr().bullets([
        "scripts/ingest.py — bulk load JSONL or a Hugging Face dataset via POST /documents",
        "scripts/benchmark.py — concurrent load test of POST /search, reports p50/p95/p99",
    ])
    ops, _ = p.box(40, 420, 220, ops_l, "script")

    # docker compose boundary
    p.vertex(320, 110, 1100, 760, "<b>Docker Compose host</b> (docker-compose.yml)",
             "rounded=1;arcSize=1;whiteSpace=wrap;html=1;dashed=1;fillColor=none;strokeColor=#333333;"
             "verticalAlign=top;align=left;spacingLeft=10;fontSize=12;")

    # api container
    p.vertex(350, 150, 560, 690,
             "<b>vectorflow-api</b> container — image <i>vectorflow:latest</i> (python:3.12-slim, CPU torch, model baked in)<br>"
             "uvicorn · WEB_CONCURRENCY=2 workers · OMP_NUM_THREADS=4 · port 8000 · non-root user · HEALTHCHECK /health",
             "rounded=1;arcSize=2;whiteSpace=wrap;html=1;fillColor=#f0f7ee;strokeColor=#82b366;verticalAlign=top;"
             "align=left;spacingLeft=10;spacingTop=4;fontSize=11;")

    http_l = Label(520).title("HTTP Layer", "app/main.py · app/api.py · app/schemas.py").hr().bullets([
        "FastAPI app factory create_app() with lifespan startup/shutdown",
        "Routes: /documents, /search, /sessions, /health (+ OpenAPI /docs)",
        "Pydantic request/response validation (limits on k, batch size, query length)",
        "Middleware adds X-Response-Time-Ms header to every response",
    ])
    http, hh = p.box(370, 215, 520, http_l, "api")
    y = 215 + hh + 20
    emb_l = Label(250).title("Embedding Service", "app/embeddings.py · HFEmbedder").hr().bullets([
        "all-MiniLM-L6-v2 → 384-dim L2-normalised vectors",
        "LRU cache (4096) for query vectors",
        "Micro-batching of concurrent queries into one forward pass",
        "Model lock prevents CPU oversubscription",
    ])
    emb, eh = p.box(370, y, 250, emb_l, "emb")
    ses_l = Label(250).title("Session Service", "app/sessions.py").hr().bullets([
        "Session model: context vector, query history, seen ids",
        "blend_query / record_query context maths",
        "RedisSessionStore (prod) or InMemorySessionStore (fallback)",
    ])
    ses, sh = p.box(640, y, 250, ses_l, "sess")
    y2 = y + max(eh, sh) + 20
    vs_l = Label(520).title("Vector Store Adapter", "app/store.py · ElasticVectorStore").hr().bullets([
        "Creates/validates index (dense_vector int8_hnsw, cosine), race-safe across workers",
        "Bulk indexing, filtered kNN search, delete, count, ping",
        "Metadata filters → term/terms on flattened field; exclude-seen → ids must_not",
    ])
    vs, vh = p.box(370, y2, 520, vs_l, "store")
    cfg = p.simple(370, y2 + vh + 20, 520, 50,
                   "<b>Configuration</b> — app/config.py Settings (pydantic-settings), all overridable via <b>VF_*</b> env vars / .env",
                   "core")

    es_l = Label(370).title("Elasticsearch 8.15.3", "single node · port 9200 · volume esdata").hr().bullets([
        "API calls: _bulk, _search (knn), _count, indices.*, cluster.health",
        "Index vectorflow-docs: 1 shard, 0 replicas, refresh 1s",
        "embedding: dense_vector 384, cosine, int8_hnsw (m=16, ef_construction=100)",
        "title/text: text · metadata: flattened · created_at: date",
        "Security disabled for dev; disk watermark check disabled (dev only)",
        "Heap 1 GB (ES_JAVA_OPTS)",
    ])
    es, _ = p.box(1020, 200, 370, es_l, "store")
    rd_l = Label(370).title("Redis 7 (alpine)", "internal network only · no host port").hr().bullets([
        "API calls: GET, SET EX, DEL, PING",
        "Key vf:session:<id> → session JSON",
        "SET ... EX 1800 (sliding TTL refreshed on each save)",
        "Ephemeral: no RDB/AOF persistence",
        "maxmemory 256mb, policy volatile-lru",
    ])
    rd, _ = p.box(1020, 520, 370, rd_l, "sess")

    hf = p.simple(1480, 170, 220, 90,
                  "<b>Hugging Face Hub</b><br>sentence-transformers/all-MiniLM-L6-v2<br><i>(build time only)</i>", "ext")
    img = p.simple(1480, 330, 220, 90,
                   "<b>Docker image build</b><br>Dockerfile downloads model into HF_HOME; runtime sets HF_HUB_OFFLINE=1 → becomes the vectorflow-api image",
                   "core")

    p.edge(client, http, "HTTP/JSON :8000", entry=(0, 0.3))
    p.edge(ops, http, "", entry=(0, 0.7))
    p.edge(http, emb, "embed text", exit_=(0.25, 1), entry=(0.5, 0))
    p.edge(http, ses, "get/save session", exit_=(0.75, 1), entry=(0.5, 0))
    p.edge(emb, vs, "query vector", exit_=(0.5, 1), entry=(0.25, 0))
    p.edge(ses, vs, "exclude seen ids", exit_=(0.5, 1), entry=(0.75, 0))
    p.edge(vs, es, "HTTP :9200", exit_=(1, 0.3), entry=(0, 0.5))
    p.edge(ses, rd, "RESP :6379", exit_=(1, 0.5), entry=(0, 0.4))
    p.edge(hf, img, "model download", style="dashed=1;")

    notes = Label(1660).title("Key Design Decisions & Non-Functional Characteristics").hr()
    notes.bullets([
        "Stateless API workers: all session state lives in Redis, so the API can scale horizontally behind a load balancer.",
        "Latency (20k AG News docs, 12-core laptop): p99 27 ms at concurrency 1, 87 ms at concurrency 8 (125 req/s), 161 ms at 16 (148 req/s). ES kNN stays ~10 ms; CPU embedding dominates under load.",
        "Latency levers: int8-quantised HNSW, query-embedding LRU cache, micro-batching, WEB_CONCURRENCY × OMP_NUM_THREADS ≤ cores, model baked into image + warm-up at startup.",
        "Continuous query context: each session keeps an exponentially decaying average of past query vectors that is blended into new queries.",
        "Resilience: API waits for ES (30 retries × 2 s), compose healthchecks gate startup order, restart: unless-stopped, /health returns 503 when a dependency is down.",
        "Scale-out paths: more API replicas, GPU embedding (VF_EMBEDDING_DEVICE=cuda), ES shards/replicas for larger corpora.",
    ])
    p.box(40, 900, 1660, notes, "note")

    legend = Label(220).title("Legend").hr().bullets([
        "Green = HTTP/API layer", "Blue = embeddings", "Orange = Elasticsearch/vector store",
        "Purple = sessions/Redis", "Red = operator scripts", "Dashed arrow = build-time",
    ])
    p.box(1480, 480, 220, legend, "ext")
    pages.append(p)

    # ---------------------------------------------------------------- 2. functional modules
    p = Page("2. Functional Modules")
    p.heading(40, 20, 1600, "VectorFlow — High Level Design: Functional Modules & Responsibilities")
    mods = [
        ("Document Ingestion", "api", [
            "Accepts 1–1000 documents per request: optional id, optional title, text, free-form metadata.",
            "Embeds \"title. text\" (or text) with the document prefix, in chunks of 64.",
            "Bulk-indexes into Elasticsearch; ids are generated (uuid4) when absent; re-using an id overwrites.",
            "Optional refresh=wait_for so documents are searchable on return; scripts use refresh=false for speed.",
            "Returns indexed count, failed count, ids and took_ms.",
            "Delete by id (404 if the document does not exist).",
        ]),
        ("Semantic Search", "store", [
            "Embeds the query (cached + micro-batched) into a 384-dim normalised vector.",
            "Approximate kNN on the HNSW index: k results (1–100), num_candidates = k × 10.",
            "Exact-match metadata filters (single value → term, list → terms; booleans as \"true\"/\"false\").",
            "Returns id, cosine score ((1+cos)/2), title, text, metadata, plus embed/search/total timings.",
        ]),
        ("Stateful Sessions", "sess", [
            "Create / inspect / delete sessions; sessions expire after 30 min idle (sliding TTL).",
            "Context vector = decaying average of query vectors (decay 0.6); blended into new queries (weight 0.3).",
            "use_context=false opts a single query out of blending.",
            "exclude_seen=true skips documents already returned in the session (up to 500 remembered).",
            "Keeps the last 20 query strings for inspection.",
        ]),
        ("Embedding Engine", "emb", [
            "Hugging Face sentence-transformers model loaded once per worker at startup and warmed up.",
            "Configurable model, device, batch size and query/document prefixes (for e5/bge models).",
            "LRU cache of query vectors (4096 entries) — repeated queries skip the model.",
            "Concurrent queries coalesced into one forward pass; one forward pass at a time per worker.",
        ]),
        ("Health & Observability", "core", [
            "GET /health pings Elasticsearch and the session store and reports document count and model.",
            "200 \"ok\" when all dependencies are up, 503 \"degraded\" otherwise (used by Docker HEALTHCHECK).",
            "X-Response-Time-Ms header on every response; per-stage timings in search responses.",
            "Structured logging for startup, index creation and bulk failures.",
        ]),
        ("Configuration & Deployment", "core", [
            "All settings in one Settings class, overridable via VF_* environment variables or .env.",
            "Three containers: api, elasticsearch, redis; healthchecks gate startup order.",
            "Image ships CPU-only torch and the pre-downloaded model; runs as non-root.",
            "Startup validates index vector dimension against the model to prevent silent corruption.",
        ]),
        ("Operator Tooling", "script", [
            "ingest.py: stream JSONL or Hugging Face datasets, batch to POST /documents, progress + docs/s.",
            "benchmark.py: concurrent /search load with unique queries, client and server latency percentiles.",
            "Test suite: fake embedder + in-memory vector store, so tests need neither torch nor Elasticsearch.",
        ]),
    ]
    xs = [40, 590, 1140]
    ys = [80, 80, 80]
    for i, (title, kind, items) in enumerate(mods):
        col = i % 3
        lab = Label(520).title(title).hr().bullets(items)
        _, h = p.box(xs[col], ys[col], 520, lab, kind)
        ys[col] += h + 30
    pages.append(p)

    # ---------------------------------------------------------------- 3. request flows
    p = Page("3. Request Flows")
    p.heading(40, 20, 1800, "VectorFlow — High Level Design: Key Request Flows")

    p.heading(40, 80, 1000, "A. Semantic search (POST /search)", 16)
    flow(p, 40, 125, [
        ("Validate request", "SearchRequest: query 1–2048 chars, k 1–100, filters, session_id, use_context, exclude_seen"),
        ("Load session", "If session_id: GET from Redis. Missing/expired → 404"),
        ("Embed query", "LRU cache hit ≈1 ms; miss → micro-batched model pass ≈8 ms"),
        ("Blend context", "If session has context and use_context: normalize(0.7·q + 0.3·ctx)"),
        ("kNN search", "ES knn: k, num_candidates=k×10, metadata filters, must_not seen ids"),
        ("Update session", "Fold query vector into context (decay 0.6), append query, add result ids to seen"),
        ("Save session", "SET vf:session:<id> EX 1800 (refreshes TTL)"),
        ("Respond", "hits + context_applied + timings {embed, search, total}"),
    ], w=190, h=100, gap=30, kind="store")

    p.heading(40, 300, 1000, "B. Document ingestion (POST /documents)", 16)
    flow(p, 40, 345, [
        ("Read source", "ingest.py streams JSONL lines or a Hugging Face dataset"),
        ("Batch", "Groups of 256 documents (configurable --batch-size)"),
        ("Validate", "IndexRequest: 1–1000 docs, text required"),
        ("Compose text", "\"title. text\" when a title exists, else text"),
        ("Embed", "Chunks of 64 under the model lock (queries can interleave)"),
        ("Bulk index", "async_bulk to ES; ids generated if absent; created_at stamped"),
        ("Respond", "indexed, failed, ids, took_ms; script prints docs/s"),
    ], w=190, h=90, gap=30, kind="api")

    p.heading(40, 510, 1000, "C. Session lifecycle", 16)
    flow(p, 40, 555, [
        ("Create", "POST /sessions → new uuid, saved to Redis with TTL → 201"),
        ("Search within session", "POST /search with session_id; context grows with each query"),
        ("Inspect", "GET /sessions/{id} → queries, seen_count, has_context"),
        ("End", "DELETE /sessions/{id} → 204, or automatic expiry after 30 min idle"),
    ], w=260, h=80, gap=40, kind="sess")

    p.heading(40, 710, 1000, "D. Service startup (FastAPI lifespan, per worker)", 16)
    flow(p, 40, 755, [
        ("Load model", "HFEmbedder in a thread (from baked HF cache, offline)"),
        ("Connect ES", "AsyncElasticsearch; wait for cluster yellow (30 × 2 s retries)"),
        ("Ensure index", "Create if missing (race-safe), check vector dims, wait index yellow"),
        ("Session store", "Redis if VF_REDIS_URL set, otherwise in-memory"),
        ("Warm up", "One embedding pass so the first request is not slow"),
        ("Ready", "Services on app.state; shutdown closes ES and Redis clients"),
    ], w=210, h=85, gap=36, kind="core")
    pages.append(p)

    # ---------------------------------------------------------------- 4. API contract
    p = Page("4. API Endpoints")
    p.heading(40, 20, 1600, "VectorFlow — High Level Design: REST API Contract")
    eps = [
        ("POST /documents", "api", "Index documents",
         ["Body: {documents: [{id?, title?, text, metadata?}] (1–1000), refresh: bool = true}",
          "200: {indexed, failed, ids[], took_ms}", "422: validation error"]),
        ("DELETE /documents/{doc_id}", "api", "Delete a document",
         ["204: deleted", "404: document not found"]),
        ("POST /search", "store", "Semantic kNN search, optionally within a session",
         ["Body: {query (1–2048), k = 10 (1–100), session_id?, filters?: {key: value | [values]}, use_context = true, exclude_seen = false}",
          "200: {query, session_id, context_applied, hits[{id, score, title, text, metadata}], timings{embed_ms, search_ms, total_ms}}",
          "404: session not found or expired", "422: validation error"]),
        ("POST /sessions", "sess", "Start a session",
         ["201: {id, created_at, updated_at, queries[], seen_count, has_context}"]),
        ("GET /sessions/{session_id}", "sess", "Inspect a session",
         ["200: SessionOut", "404: not found or expired"]),
        ("DELETE /sessions/{session_id}", "sess", "End a session",
         ["204: deleted", "404: not found or expired"]),
        ("GET /health", "core", "Dependency health",
         ["200: {status: \"ok\", elasticsearch: true, sessions: true, model, documents}",
          "503: status \"degraded\" when ES or the session store is unreachable"]),
        ("GET /docs · /openapi.json", "core", "Auto-generated OpenAPI / Swagger UI",
         ["Interactive documentation generated by FastAPI from the Pydantic schemas"]),
    ]
    xs, ys = [40, 860], [80, 80]
    for i, (ep, kind, title, lines) in enumerate(eps):
        col = 0 if ys[0] <= ys[1] else 1
        lab = Label(780).title(ep, title).hr().bullets(lines)
        _, h = p.box(xs[col], ys[col], 780, lab, kind)
        ys[col] += h + 24
    hdr = Label(1600).text("Every response carries the X-Response-Time-Ms header. All bodies are JSON. No authentication in this version (intended to sit behind a gateway).")
    p.box(40, max(ys) + 10, 1600, hdr, "note")
    pages.append(p)
    return pages


# ============================================================================= LLD

def lld() -> list[Page]:
    pages = []
    W = 520

    # ---------------------------------------------------------------- 1. modules & functions
    p = Page("1. Modules & Functions")
    p.heading(40, 20, 2300, "VectorFlow — Low Level Design: Every Module, Class and Function")

    config = Label(W).title("app/config.py", "configuration").hr()
    config.item("class Settings(BaseSettings)",
                "All runtime configuration. env_prefix=VF_, reads .env, ignores unknown keys. Fields: es_url, es_api_key, "
                "es_index, es_timeout_seconds=10, es_startup_retries=30, redis_url, embedding_model, embedding_device=cpu, "
                "embedding_batch_size=64, query_prefix, document_prefix, query_cache_size=4096, num_candidates_factor=10, "
                "session_ttl_seconds=1800, session_context_weight=0.3, session_decay=0.6, session_history_size=20, session_max_seen=500.")
    config.item("get_settings() -> Settings",
                "@lru_cache singleton: parses the environment once and returns the same Settings instance.")

    main = Label(W).title("app/main.py", "application factory & lifecycle").hr()
    main.item("create_app(settings=None, *, embedder=None, store=None, sessions=None) -> FastAPI",
              "Builds the FastAPI app. Any component can be injected (tests do this); otherwise each is built from Settings. "
              "Registers lifespan, the timing middleware and the API router.")
    main.item("lifespan(app)  [async context manager, nested]",
              "Startup per worker, using AsyncExitStack for cleanup:\n"
              "1) load HFEmbedder in a thread pool; 2) create AsyncElasticsearch, register close(), wait_until_ready(); "
              "3) store.ensure_index(); 4) RedisSessionStore if redis_url else InMemorySessionStore, register close(); "
              "5) warm-up embed; 6) publish settings/embedder/store/sessions on app.state. On shutdown or failed startup, clients are closed.")
    main.item("response_time_header(request, call_next)  [HTTP middleware]",
              "Measures wall time around the request and sets X-Response-Time-Ms (2 dp).")
    main.item("app = create_app()", "Module-level ASGI app used by uvicorn (app.main:app).")

    api = Label(W).title("app/api.py", "HTTP routes (APIRouter)").hr()
    api.item("_ms(start, end) -> float", "Converts a perf_counter interval to milliseconds rounded to 2 dp.")
    api.item("_services(request) -> (Settings, Embedder, VectorStore, SessionStore)",
             "Fetches the singletons placed on app.state by lifespan.")
    api.item("_session_out(session) -> SessionOut",
             "Maps the internal Session to its API shape: seen_count = len(seen_ids), has_context = context is not None.")
    api.item("GET /health  health(request, response) -> HealthResponse",
             "store.ping() + sessions.ping(); store.count() when ES is up. Sets 503 and status \"degraded\" if either is down.")
    api.item("POST /documents  index_documents(body: IndexRequest, request) -> IndexResponse",
             "model_dump() docs, builds text \"title. text\", embed_documents() in thread pool, "
             "store.index_documents(refresh=body.refresh), returns indexed/failed/ids/took_ms.")
    api.item("DELETE /documents/{doc_id}  delete_document(doc_id, request)",
             "store.delete(); 204 on success, 404 if it did not exist.")
    api.item("POST /search  search(body: SearchRequest, request) -> SearchResponse",
             "1) load session if session_id (404 if missing); 2) embed_query in thread pool; "
             "3) context_applied = session and use_context and session.context; blend_query(weight=session_context_weight); "
             "4) store.search(k, num_candidates=k×num_candidates_factor, filters, exclude_ids=seen_ids if exclude_seen); "
             "5) record_query + sessions.save; 6) build response with timings embed/search/total.")
    api.item("POST /sessions  create_session(request) -> SessionOut  [201]", "sessions.create().")
    api.item("GET /sessions/{session_id}  get_session(...) -> SessionOut", "404 if missing or expired.")
    api.item("DELETE /sessions/{session_id}  delete_session(...)  [204]", "404 if missing or expired.")

    emb = Label(W).title("app/embeddings.py", "Hugging Face embedding service").hr()
    emb.item("class Embedder(Protocol)", "Interface: dim, model_name, embed_query(text), embed_documents(texts). Lets tests inject a fake.")
    emb.item("class HFEmbedder", "sentence-transformers implementation. All vectors float32 and L2-normalised (cosine == dot).")
    emb.item("__init__(model_name, device='cpu', batch_size=64, query_prefix='', document_prefix='', cache_size=4096)",
             "Lazily imports sentence_transformers (keeps torch out of tests), loads the model, reads dim "
             "(get_embedding_dimension / get_sentence_embedding_dimension), creates _model_lock, _pending queue + "
             "_pending_lock, and wraps _encode_query in an lru_cache.")
    emb.item("_run_model(texts) -> ndarray[n, dim]",
             "model.encode(normalize_embeddings=True, convert_to_numpy=True, batch_size, no progress bar) → float32. No locking.")
    emb.item("_encode(texts) -> ndarray", "_run_model under _model_lock (one forward pass at a time per worker).")
    emb.item("_encode_query(text) -> ndarray[dim]  (micro-batching)",
             "Enqueue (prefix+text, Future); acquire _model_lock; if own Future not yet done, drain the whole queue and "
             "encode it in one pass, resolving every Future (or set_exception on all). Vectors are made read-only because "
             "they are shared through the cache.")
    emb.item("embed_query(text) -> ndarray", "Public entry: LRU-cached _encode_query.")
    emb.item("embed_documents(texts) -> ndarray[n, dim]",
             "Adds document_prefix, encodes in chunks of batch_size, lock taken per chunk so queries interleave; concatenates.")
    emb.item("cache_info() -> {hits, misses, size}", "Query-cache statistics.")

    store = Label(W).title("app/store.py", "Elasticsearch vector store").hr()
    store.item("class VectorStore(Protocol)",
               "Interface: ensure_index, index_documents, delete, search, count, ping.")
    store.item("_as_keyword(value) -> str",
               "Flattened fields index leaves as keyword strings: bool → \"true\"/\"false\", others str().")
    store.item("build_filter(filters, exclude_ids) -> dict",
               "bool query: filter = [term metadata.<k>] for scalars / [terms metadata.<k>] for lists; "
               "must_not = [ids exclude_ids] when given. Used as the knn pre-filter.")
    store.item("class ElasticVectorStore(client, index, dim)", "Holds AsyncElasticsearch client, index name and vector dim.")
    store.item("wait_until_ready(retries=30, delay=2.0)",
               "Polls cluster.health(wait_for_status=yellow); on ConnectionError sleeps and retries; RuntimeError when exhausted.")
    store.item("ensure_index()",
               "Create the index if missing, then read its mapping and raise if embedding.dims != model dim; finally wait for index health yellow (30 s).")
    store.item("_create_index()",
               "indices.create: 1 shard, 0 replicas, refresh 1s; mapping title/text=text, metadata=flattened, created_at=date, "
               "embedding=dense_vector(dim, cosine, int8_hnsw m=16 ef_construction=100). Swallows resource_already_exists_exception (multi-worker race).")
    store.item("index_documents(docs, vectors, refresh=False) -> (ids, failed)",
               "Assigns uuid4 hex ids where missing, stamps created_at (UTC ISO), builds bulk actions, async_bulk(raise_on_error=False, "
               "refresh=wait_for if requested). Returns successful ids and failure count; logs first failures.")
    store.item("delete(doc_id) -> bool", "client.delete(refresh=wait_for, ignore 404); True if result == \"deleted\".")
    store.item("search(vector, k, num_candidates, filters=None, exclude_ids=None) -> list[dict]",
               "knn{field: embedding, query_vector, k, num_candidates=max(nc, k), filter=build_filter(...)}, size=k, "
               "source_excludes=[embedding]. Maps hits → {id, score, title, text, metadata}.")
    store.item("count() -> int", "Document count of the index.")
    store.item("ping() -> bool", "client.ping(); any exception → False.")

    sess = Label(W).title("app/sessions.py", "stateful search sessions").hr()
    sess.item("_normalize(v) -> ndarray", "v / ||v|| as float32 (zero vector returned unchanged).")
    sess.item("@dataclass Session",
              "id, created_at, updated_at, queries: list[str], seen_ids: list[str], context: ndarray | None.")
    sess.item("Session.new() -> Session", "uuid4 hex id, created_at = updated_at = now.")
    sess.item("Session.to_json() -> str", "JSON; context stored as base64 of float32 bytes (compact, lossless).")
    sess.item("Session.from_json(raw) -> Session", "Inverse of to_json; decodes context back into a float32 array.")
    sess.item("blend_query(query_vec, context, weight) -> ndarray",
              "Returns query_vec unchanged if no context or weight ≤ 0; else normalize((1−w)·q + w·context).")
    sess.item("record_query(session, query, query_vec, result_ids, decay, history_size, max_seen)",
              "In place: context = q (first query) or normalize(decay·context + (1−decay)·q); queries keeps last history_size; "
              "seen_ids is an ordered set (re-seen ids move to the end) trimmed to max_seen; updated_at = now.")
    sess.item("class SessionStore(Protocol)", "create, get, save, delete, ping, close.")
    sess.item("class InMemorySessionStore(ttl_seconds)",
              "dict id → (expires_at, json). get() lazily evicts expired entries; save() resets expiry. Single process only.")
    sess.item("class RedisSessionStore(url, ttl_seconds, prefix='vf:session:')",
              "redis.asyncio client. _key(id) = prefix + id; create = new + save; get = GET + from_json; "
              "save = SET EX ttl (sliding TTL); delete = DEL > 0; ping = PING (exceptions → False); close = aclose().")

    schemas = Label(W).title("app/schemas.py", "Pydantic request/response models").hr()
    schemas.item("DocumentIn", "id?: str, title?: str, text: str (min 1), metadata: dict = {}")
    schemas.item("IndexRequest / IndexResponse", "documents: list[DocumentIn] (1–1000), refresh = true  →  indexed, failed, ids, took_ms")
    schemas.item("SearchRequest",
                 "query (1–2048), k = 10 (1–100), session_id?, filters?: dict[str, scalar | list[scalar]], use_context = true, exclude_seen = false")
    schemas.item("SearchHit / Timings / SearchResponse",
                 "id, score, title, text, metadata · embed_ms, search_ms, total_ms · query, session_id, context_applied, hits, timings")
    schemas.item("SessionOut", "id, created_at, updated_at, queries, seen_count, has_context")
    schemas.item("HealthResponse", "status, elasticsearch, sessions, model, documents?")

    ingest = Label(W).title("scripts/ingest.py", "bulk loader (HTTP client)").hr()
    ingest.item("read_jsonl(path) -> Iterator[dict]", "Yields one document per non-empty JSONL line.")
    ingest.item("read_hf(name, split, text_field, title_field, limit) -> Iterator[dict]",
                "Streams a Hugging Face dataset; id = <name>-<split>-<i>; scalar non-text columns become metadata.")
    ingest.item("batched(it, size) -> Iterator[list[dict]]", "Chunks an iterator into lists of size (last may be shorter).")
    ingest.item("main()",
                "Args: --jsonl | --hf-dataset, --split, --text-field, --title-field, --limit, --batch-size 256, --api. "
                "POSTs each batch with refresh=false, prints running count and docs/s, exits 1 if any failed.")

    bench = Label(W).title("scripts/benchmark.py", "latency / throughput benchmark").hr()
    bench.item("pct(values, p) -> float", "Nearest-rank percentile.")
    bench.item("run(args)  [async]",
               "httpx.AsyncClient; optional shared session; semaphore limits concurrency; warm-up requests then reset stats; "
               "gathers N requests; prints throughput and p50/p95/p99/mean for client latency and server embed/search/total.")
    bench.item("one(i)  [nested async]",
               "Builds a query (unique suffix unless --allow-cache), times POST /search, records server timings, counts errors.")
    bench.item("main()", "Args: --api, --requests 500, --concurrency 8, --k 10, --warmup 20, --session, --allow-cache.")

    tests = Label(W).title("tests/", "test doubles & suites (pytest)").hr()
    tests.item("FakeEmbedder", "Bag-of-words hashing into 256 dims; texts sharing words get similar vectors. No torch.")
    tests.item("FakeVectorStore", "Brute-force cosine with the same filter / exclude semantics and score scale as ES.")
    tests.item("SlowModel + make_embedder()", "Fake SentenceTransformer used to test micro-batching, cache and error propagation.")
    tests.item("test_api.py · test_sessions.py · test_embeddings.py",
               "Endpoints, validation, filters, sessions (context steering, exclude_seen), maths, serialisation, TTL, batching. 18 tests.")

    ids = {}
    ids.update(column(p, 40, 80, W, [("config", config, "core"), ("main", main, "core"), ("schemas", schemas, "schema")]))
    ids.update(column(p, 700, 80, W, [("api", api, "api"), ("tests", tests, "ext")]))
    ids.update(column(p, 1360, 80, W, [("emb", emb, "emb"), ("sess", sess, "sess")]))
    ids.update(column(p, 2020, 80, W, [("store", store, "store"), ("ingest", ingest, "script"), ("bench", bench, "script")]))

    dep = "dashed=1;endArrow=open;endFill=0;"
    p.edge(ids["main"], ids["config"], "get_settings()", dep, exit_=(0.5, 0), entry=(0.5, 1))
    p.edge(ids["main"], ids["api"], "include_router", dep, exit_=(1, 0.3), entry=(0, 0.2))
    p.edge(ids["api"], ids["schemas"], "validates", dep, exit_=(0, 0.8), entry=(1, 0.3))
    p.edge(ids["api"], ids["emb"], "embeds via", dep, exit_=(1, 0.15), entry=(0, 0.15))
    p.edge(ids["api"], ids["sess"], "sessions", dep, exit_=(1, 0.6), entry=(0, 0.2))
    p.edge(ids["api"], ids["store"], "search / index / delete / count", dep, exit_=(0.6, 0), entry=(0.3, 0))
    pages.append(p)

    # ---------------------------------------------------------------- 2. class diagram (interfaces)
    p = Page("2. Interfaces & Implementations")
    p.heading(40, 20, 1800, "VectorFlow — Low Level Design: Interfaces (Protocols) and Implementations")
    uml = "swimlane;fontStyle=1;childLayout=stackLayout;horizontal=1;startSize=30;horizontalStack=0;resizeParent=1;" \
          "resizeParentMax=0;resizeLast=0;collapsible=0;marginBottom=0;html=1;fontSize=12;"

    def uml_class(x, y, w, name, kind, fields, methods):
        fill, stroke = COLORS[kind]
        rows = len(fields) + len(methods)
        h = 30 + rows * 20 + (8 if fields and methods else 0) + 6
        cid = p.vertex(x, y, w, h, name, uml + f"fillColor={fill};strokeColor={stroke};")
        yy = 30
        rowst = "text;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;spacingLeft=6;html=1;fontSize=11;fontFamily=Courier New;"
        for f in fields:
            p.vertex(0, yy, w, 20, esc(f), rowst, parent=cid)
            yy += 20
        if fields and methods:
            p.vertex(0, yy, w, 8, "", "line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;html=1;", parent=cid)
            yy += 8
        for m in methods:
            p.vertex(0, yy, w, 20, esc(m), rowst, parent=cid)
            yy += 20
        return cid

    e_proto = uml_class(40, 80, 380, "«Protocol» Embedder", "emb",
                        ["+ dim: int", "+ model_name: str"],
                        ["+ embed_query(text) -> ndarray", "+ embed_documents(texts) -> ndarray"])
    e_impl = uml_class(40, 300, 380, "HFEmbedder", "emb",
                       ["- _model: SentenceTransformer", "- _batch_size: int", "- _query_prefix / _document_prefix: str",
                        "- _model_lock: threading.Lock", "- _pending: list[(str, Future)]", "- _pending_lock: threading.Lock",
                        "- _cached_query: lru_cache(_encode_query)"],
                       ["- _run_model(texts) -> ndarray", "- _encode(texts) -> ndarray", "- _encode_query(text) -> ndarray",
                        "+ embed_query(text) -> ndarray", "+ embed_documents(texts) -> ndarray", "+ cache_info() -> dict"])
    v_proto = uml_class(500, 80, 520, "«Protocol» VectorStore", "store", [],
                        ["+ ensure_index()", "+ index_documents(docs, vectors, refresh) -> (ids, failed)",
                         "+ delete(doc_id) -> bool", "+ search(vector, k, num_candidates, filters, exclude_ids) -> list[dict]",
                         "+ count() -> int", "+ ping() -> bool"])
    v_impl = uml_class(500, 300, 520, "ElasticVectorStore", "store",
                       ["+ client: AsyncElasticsearch", "+ index: str", "+ dim: int"],
                       ["+ wait_until_ready(retries, delay)", "+ ensure_index()", "- _create_index()",
                        "+ index_documents(docs, vectors, refresh)", "+ delete(doc_id)", "+ search(vector, k, num_candidates, filters, exclude_ids)",
                        "+ count()", "+ ping()"])
    s_proto = uml_class(1100, 80, 380, "«Protocol» SessionStore", "sess", [],
                        ["+ create() -> Session", "+ get(id) -> Session | None", "+ save(session)", "+ delete(id) -> bool",
                         "+ ping() -> bool", "+ close()"])
    s_mem = uml_class(1100, 300, 380, "InMemorySessionStore", "sess",
                      ["+ ttl: int", "- _data: dict[id, (expires_at, json)]"],
                      ["+ create / get / save / delete", "+ ping / close"])
    s_red = uml_class(1100, 470, 380, "RedisSessionStore", "sess",
                      ["- _redis: redis.asyncio.Redis", "+ ttl: int", "+ prefix = 'vf:session:'"],
                      ["- _key(id) -> str", "+ create / get / save / delete", "+ ping / close"])
    sess_cls = uml_class(1560, 80, 360, "«dataclass» Session", "sess",
                         ["+ id: str", "+ created_at: float", "+ updated_at: float", "+ queries: list[str]",
                          "+ seen_ids: list[str]", "+ context: ndarray | None"],
                         ["+ new() -> Session  «classmethod»", "+ to_json() -> str", "+ from_json(raw) -> Session  «classmethod»"])
    funcs = uml_class(1560, 380, 360, "sessions module functions", "sess", [],
                      ["_normalize(v)", "blend_query(q, context, weight)", "record_query(session, query, q, ids, ...)"])
    fakes = uml_class(40, 700, 380, "Test doubles", "ext", [],
                      ["FakeEmbedder  ⟶ Embedder", "FakeVectorStore  ⟶ VectorStore", "InMemorySessionStore  ⟶ SessionStore"])
    app_cls = uml_class(500, 640, 520, "FastAPI app.state  (set by lifespan)", "api",
                        ["+ settings: Settings", "+ embedder: Embedder", "+ store: VectorStore", "+ sessions: SessionStore"], [])

    real = "endArrow=block;endFill=0;dashed=1;"
    p.edge(e_impl, e_proto, "implements", real)
    p.edge(v_impl, v_proto, "implements", real)
    p.edge(s_mem, s_proto, "implements", real, exit_=(0.5, 0), entry=(0.5, 1))
    p.edge(s_red, s_proto, "implements", real, exit_=(0, 0.5), entry=(0, 0.5))
    p.edge(s_proto, sess_cls, "stores / returns", "endArrow=open;endFill=0;", exit_=(1, 0.3), entry=(0, 0.3))
    p.edge(funcs, sess_cls, "mutates / reads", "endArrow=open;endFill=0;", exit_=(0.5, 0), entry=(0.5, 1))
    agg = "endArrow=diamondThin;endFill=1;startArrow=none;endSize=14;"
    p.edge(e_proto, app_cls, "", agg, exit_=(1, 0.8), entry=(0, 0.4))
    p.edge(v_impl, app_cls, "", agg, exit_=(0.5, 1), entry=(0.5, 0))
    p.edge(s_red, app_cls, "", agg, exit_=(0.5, 1), entry=(1, 0.5))
    pages.append(p)

    # ---------------------------------------------------------------- 3. search sequence
    p = Page("3. Search Sequence")
    p.heading(40, 20, 1800, "VectorFlow — Low Level Design: POST /search Sequence (session, cache miss)")
    actors = ["Client", "Middleware\nresponse_time_header", "api.search()", "RedisSessionStore", "HFEmbedder",
              "sessions\nblend/record", "ElasticVectorStore", "Elasticsearch", "Redis"]
    kinds = ["ext", "core", "api", "sess", "emb", "sess", "store", "store", "sess"]
    X0, DX, TOP, BOTTOM = 60, 200, 80, 1180
    xs = []
    for i, (a, k) in enumerate(zip(actors, kinds)):
        x = X0 + i * DX
        xs.append(x + 80)
        p.simple(x, TOP, 160, 50, f"<b>{esc(a).replace(chr(10), '<br>')}</b>", k)

    y = TOP + 90
    ret = "dashed=1;endArrow=open;endFill=0;"

    def msg(a, b, text, style="", dy=46):
        nonlocal y
        p.line(xs[a], y, xs[b], y, esc(text), style)
        y += dy

    def note(a, text, w=180, h=56):
        nonlocal y
        p.simple(xs[a] + 10, y - 22, w, h, f'<font style="font-size:10px">{esc(text)}</font>', "note",
                 "align=left;spacingLeft=4;verticalAlign=middle;")
        y += h + 6

    msg(0, 1, "POST /search {query, k, session_id, filters, use_context, exclude_seen}")
    note(1, "start = perf_counter()", h=34)
    msg(1, 2, "call_next(request) → Pydantic validates SearchRequest (422 on error)")
    note(2, "_services(request) → settings, embedder, store, sessions", h=40)
    msg(2, 3, "get(session_id)")
    msg(3, 8, "GET vf:session:<id>")
    msg(8, 3, "JSON | nil", ret)
    msg(3, 2, "Session (or None → HTTPException 404)", ret)
    msg(2, 4, "run_in_threadpool(embed_query, query)")
    note(4, "lru_cache miss → _encode_query: enqueue (text, Future), acquire _model_lock, drain queue, one forward pass, resolve Futures", w=190, h=84)
    msg(4, 2, "query_vec (384-d, normalised, read-only)", ret)
    msg(2, 5, "blend_query(query_vec, session.context, 0.3)")
    msg(5, 2, "normalize(0.7·q + 0.3·ctx)", ret)
    msg(2, 6, "search(vec, k, num_candidates=k×10, filters, exclude_ids=seen_ids?)")
    note(6, "build_filter(): term/terms on metadata.*, must_not ids", h=40)
    msg(6, 7, "POST /<index>/_search {knn{...filter}, size=k, _source excludes embedding}")
    msg(7, 6, "hits (_id, _score, _source)", ret)
    msg(6, 2, "[{id, score, title, text, metadata}]", ret)
    msg(2, 5, "record_query(session, query, query_vec, ids, decay=0.6, history=20, max_seen=500)")
    msg(2, 3, "save(session)")
    msg(3, 8, "SET vf:session:<id> <json> EX 1800")
    msg(8, 3, "OK", ret)
    msg(2, 1, "SearchResponse {hits, context_applied, timings{embed_ms, search_ms, total_ms}}", ret)
    msg(1, 0, "200 JSON + X-Response-Time-Ms header", ret)
    for x in xs:
        p.line(x, TOP + 50, x, y, "", "dashed=1;endArrow=none;strokeColor=#999999;")
    pages.append(p)

    # ---------------------------------------------------------------- 4. algorithms
    p = Page("4. Algorithms")
    p.heading(40, 20, 1800, "VectorFlow — Low Level Design: Core Algorithms")

    # micro-batching flowchart
    p.heading(40, 70, 700, "A. HFEmbedder._encode_query — micro-batching", 15)
    dec = "rhombus;whiteSpace=wrap;html=1;fontSize=11;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    st = "rounded=1;whiteSpace=wrap;html=1;fontSize=11;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    term = "ellipse;whiteSpace=wrap;html=1;fontSize=11;fillColor=#ffffff;strokeColor=#6c8ebf;"
    a1 = p.vertex(200, 115, 260, 44, "embed_query(text)", term)
    a2 = p.vertex(200, 185, 260, 40, "lru_cache lookup", st)
    a3 = p.vertex(230, 250, 200, 80, "cache hit?", dec)
    a4 = p.vertex(540, 265, 180, 50, "return cached vector (≈1 ms)", term)
    a5 = p.vertex(200, 360, 260, 50, "with _pending_lock: append (prefix+text, Future)", st)
    a6 = p.vertex(200, 435, 260, 40, "acquire _model_lock (wait for any running pass)", st)
    a7 = p.vertex(230, 500, 200, 80, "own Future already done?", dec)
    a8 = p.vertex(200, 610, 260, 50, "with _pending_lock: batch = all pending; pending = []", st)
    a9 = p.vertex(200, 685, 260, 50, "_run_model(batch texts) — one forward pass for N queries", st)
    a10 = p.vertex(200, 760, 260, 50, "for each (Future, vec): vec read-only, set_result", st)
    a11 = p.vertex(540, 760, 180, 50, "on exception: set_exception on every Future", st)
    a12 = p.vertex(200, 840, 260, 44, "release lock → return future.result(); cache stores it", term)
    for s, t in [(a1, a2), (a2, a3), (a5, a6), (a6, a7), (a8, a9), (a9, a10), (a10, a12)]:
        p.edge(s, t)
    p.edge(a3, a4, "yes")
    p.edge(a3, a5, "no")
    p.edge(a7, a8, "no (this thread leads)")
    p.edge(a7, a12, "yes (another thread\nencoded it)", exit_=(0, 0.5), entry=(0, 0.5), points=[(110, 540), (110, 862)])
    p.edge(a9, a11, "error", "dashed=1;", exit_=(1, 0.5), entry=(0.5, 0))
    p.edge(a11, a12, "", "dashed=1;", exit_=(0.5, 1), entry=(1, 0.5))
    why = Label(330).title("Why").hr().bullets([
        "torch already uses OMP_NUM_THREADS cores per pass; parallel passes thrash the CPU.",
        "Under load N waiting queries cost ~1 pass instead of N sequential passes.",
        "Measured at concurrency 16: p99 212 → 161 ms, throughput ≈ +20%.",
    ])
    p.box(760, 380, 330, why, "note")

    # session maths
    sm = Label(640).title("B. Session context maths (app/sessions.py)").hr()
    sm.section("blend_query(q, ctx, w)  — applied before search")
    sm.text("if ctx is None or w ≤ 0:  q_search = q\nelse:  q_search = normalize((1 − w) · q + w · ctx)        default w = 0.3")
    sm.section("record_query(...)  — applied after search")
    sm.text("ctx₁ = q₁\nctxₙ = normalize(d · ctxₙ₋₁ + (1 − d) · qₙ)        default d = 0.6\n"
            "Note: the stored context uses the raw query vector qₙ, not the blended one, so context cannot amplify itself.")
    sm.text("queries  ← (queries + [query])[-20:]\n"
            "seen_ids ← ordered set; ids returned again move to the end; keep last 500\nupdated_at ← now")
    sm.section("Example")
    sm.text("\"rockets and moon landings\" → \"what are the latest missions\": space documents rank higher than with the bare query; "
            "exclude_seen then surfaces unseen documents (e.g. James Webb telescope).")
    p.box(1140, 80, 640, sm, "sess")

    # filter building
    fb = Label(640).title("C. build_filter(filters, exclude_ids) — kNN pre-filter").hr()
    fb.text('Input:  {"category": "tech", "tags": ["a", 1], "active": true},  exclude_ids = ["x"]')
    fb.text('Output: {"bool": {"filter": [\n'
            '    {"term":  {"metadata.category": "tech"}},\n'
            '    {"terms": {"metadata.tags": ["a", "1"]}},\n'
            '    {"term":  {"metadata.active": "true"}}],\n'
            '  "must_not": [{"ids": {"values": ["x"]}}]}}')
    fb.text("Applied inside knn.filter, so HNSW only considers matching documents and still returns k results when possible.")
    _, fh = p.box(1140, 560, 640, fb, "store")

    # startup / ensure_index
    p.heading(40, 920, 900, "D. Startup: lifespan + ElasticVectorStore.ensure_index", 15)
    flow(p, 40, 965, [
        ("HFEmbedder()", "Load model in thread pool; read dim"),
        ("wait_until_ready", "cluster.health yellow; ConnectionError → sleep 2 s, max 30 tries"),
        ("indices.exists?", "No → _create_index (resource_already_exists_exception ignored: another worker won)"),
        ("Dimension check", "get_mapping → embedding.dims must equal model dim, else RuntimeError"),
        ("Index health", "cluster.health(index, yellow, 30 s)"),
        ("Session store", "RedisSessionStore(url, ttl) or InMemorySessionStore(ttl)"),
        ("Warm-up + publish", "embed_documents([\"warm up\"]); set app.state.*; yield"),
        ("Shutdown", "AsyncExitStack closes Redis and ES clients (also on failed startup)"),
    ], w=200, h=95, gap=30, kind="core")
    pages.append(p)

    # ---------------------------------------------------------------- 5. data model
    p = Page("5. Data Model & Config")
    p.heading(40, 20, 1800, "VectorFlow — Low Level Design: Storage Schemas & Configuration")
    esm = Label(560).title("Elasticsearch index: vectorflow-docs", "VF_ES_INDEX").hr()
    esm.section("settings")
    esm.text("number_of_shards: 1 · number_of_replicas: 0 · refresh_interval: 1s")
    esm.section("mappings.properties")
    esm.item("_id: keyword", "Client-supplied id or uuid4 hex.")
    esm.item("title: text", "Optional; also prepended to the embedded text.")
    esm.item("text: text", "Document body (required).")
    esm.item("metadata: flattened", "Arbitrary JSON object; every leaf filterable as metadata.<key> keyword.")
    esm.item("created_at: date", "UTC ISO timestamp set at index time.")
    esm.item("embedding: dense_vector(dims=384, index=true, similarity=cosine)",
             "index_options: int8_hnsw, m=16, ef_construction=100. Excluded from _source in search responses.")
    esm.section("Score")
    esm.text("_score = (1 + cosine) / 2  ∈ [0, 1]")
    _, esh = p.box(40, 80, 560, esm, "store")

    rdm = Label(560).title("Redis session record").hr()
    rdm.item("Key", "vf:session:<32-char uuid4 hex>")
    rdm.item("Command", "SET key value EX 1800 on every save (sliding TTL); GET; DEL")
    rdm.item("Value (JSON)",
             '{"id": "...", "created_at": 1791378950.93, "updated_at": 1791378951.07, '
             '"queries": ["rockets and moon landings", ...], "seen_ids": ["doc-030", ...], '
             '"context": "<base64 of 384 × float32 = 1536 bytes>" | null}')
    rdm.item("Size", "≈ 2 KB context + history + up to 500 ids")
    rdm.item("Server config", "--save \"\" --appendonly no --maxmemory 256mb --maxmemory-policy volatile-lru")
    p.box(640, 80, 560, rdm, "sess")

    cfgl = Label(560).title("Settings (VF_* environment variables)").hr()
    for name, default, desc in [
        ("VF_ES_URL", "http://localhost:9200", "Elasticsearch endpoint"),
        ("VF_ES_API_KEY", "None", "API key when ES security is on"),
        ("VF_ES_INDEX", "vectorflow-docs", "Index name"),
        ("VF_ES_TIMEOUT_SECONDS", "10", "Request timeout"),
        ("VF_ES_STARTUP_RETRIES", "30", "Startup connection attempts (2 s apart)"),
        ("VF_REDIS_URL", "redis://localhost:6379/0", "Empty → in-memory sessions"),
        ("VF_EMBEDDING_MODEL", "all-MiniLM-L6-v2", "Any sentence-transformers model"),
        ("VF_EMBEDDING_DEVICE", "cpu", "cpu / cuda"),
        ("VF_EMBEDDING_BATCH_SIZE", "64", "Document encode chunk size"),
        ("VF_QUERY_PREFIX / VF_DOCUMENT_PREFIX", "\"\"", "e.g. \"query: \" / \"passage: \" for e5"),
        ("VF_QUERY_CACHE_SIZE", "4096", "LRU entries per worker"),
        ("VF_NUM_CANDIDATES_FACTOR", "10", "num_candidates = k × factor"),
        ("VF_SESSION_TTL_SECONDS", "1800", "Idle expiry"),
        ("VF_SESSION_CONTEXT_WEIGHT", "0.3", "w in blend_query"),
        ("VF_SESSION_DECAY", "0.6", "d in record_query"),
        ("VF_SESSION_HISTORY_SIZE", "20", "Queries kept"),
        ("VF_SESSION_MAX_SEEN", "500", "Seen ids kept"),
        ("WEB_CONCURRENCY / OMP_NUM_THREADS", "2 / 4", "uvicorn workers / torch threads per worker"),
    ]:
        cfgl.item(f"{name} = {default}", desc)
    p.box(1240, 80, 560, cfgl, "core")

    dk = Label(1160).title("Docker artefacts").hr()
    dk.item("Dockerfile",
            "python:3.12-slim → pip install CPU torch → requirements.txt → download VF_EMBEDDING_MODEL into HF_HOME=/opt/hf-cache → "
            "HF_HUB_OFFLINE=1 → copy app/ → non-root user vf (uid 1000) → HEALTHCHECK GET /health → CMD uvicorn app.main:app --host 0.0.0.0 --port 8000")
    dk.item("docker-compose.yml",
            "elasticsearch (8.15.3, single-node, security off, 1 GB heap, disk threshold off, volume esdata, curl healthcheck) · "
            "redis (7-alpine, ephemeral, redis-cli ping healthcheck, no host port) · "
            "api (build ., env VF_ES_URL / VF_REDIS_URL / WEB_CONCURRENCY / OMP_NUM_THREADS, port 8000, depends_on healthy, restart unless-stopped)")
    dk.item(".dockerignore", "Excludes .venv, tests, scripts, data, docs and .env from the build context.")
    p.box(40, 80 + esh + 30, 1160, dk, "core")
    pages.append(p)
    return pages


OUT.mkdir(parents=True, exist_ok=True)
write(OUT / "VectorFlow-HLD.drawio", hld())
write(OUT / "VectorFlow-LLD.drawio", lld())
