from time import perf_counter

from fastapi import APIRouter, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.embeddings import Embedder
from app.schemas import (
    HealthResponse,
    IndexRequest,
    IndexResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SessionOut,
    Timings,
)
from app.sessions import Session, SessionStore, blend_query, record_query
from app.store import VectorStore

router = APIRouter()


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000, 2)


def _services(request: Request) -> tuple[Settings, Embedder, VectorStore, SessionStore]:
    s = request.app.state
    return s.settings, s.embedder, s.store, s.sessions


def _session_out(session: Session) -> SessionOut:
    return SessionOut(
        id=session.id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        queries=session.queries,
        seen_count=len(session.seen_ids),
        has_context=session.context is not None,
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request, response: Response):
    _, embedder, store, sessions = _services(request)
    es_ok = await store.ping()
    sessions_ok = await sessions.ping()
    documents = await store.count() if es_ok else None
    healthy = es_ok and sessions_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "degraded",
        elasticsearch=es_ok,
        sessions=sessions_ok,
        model=embedder.model_name,
        documents=documents,
    )


@router.post("/documents", response_model=IndexResponse, tags=["documents"])
async def index_documents(body: IndexRequest, request: Request):
    _, embedder, store, _ = _services(request)
    start = perf_counter()
    docs = [d.model_dump() for d in body.documents]
    texts = [f"{d['title']}. {d['text']}" if d.get("title") else d["text"] for d in docs]
    vectors = await run_in_threadpool(embedder.embed_documents, texts)
    ids, failed = await store.index_documents(docs, vectors, refresh=body.refresh)
    return IndexResponse(indexed=len(ids), failed=failed, ids=ids, took_ms=_ms(start, perf_counter()))


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["documents"])
async def delete_document(doc_id: str, request: Request):
    _, _, store, _ = _services(request)
    if not await store.delete(doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


@router.post("/search", response_model=SearchResponse, tags=["search"])
async def search(body: SearchRequest, request: Request):
    settings, embedder, store, sessions = _services(request)
    start = perf_counter()

    session = None
    if body.session_id:
        session = await sessions.get(body.session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found or expired")

    query_vec = await run_in_threadpool(embedder.embed_query, body.query)
    embedded = perf_counter()

    context_applied = bool(session and body.use_context and session.context is not None)
    search_vec = (
        blend_query(query_vec, session.context, settings.session_context_weight) if context_applied else query_vec
    )
    hits = await store.search(
        search_vec,
        k=body.k,
        num_candidates=body.k * settings.num_candidates_factor,
        filters=body.filters,
        exclude_ids=session.seen_ids if session and body.exclude_seen else None,
    )
    searched = perf_counter()

    if session:
        record_query(
            session,
            body.query,
            query_vec,
            [h["id"] for h in hits],
            decay=settings.session_decay,
            history_size=settings.session_history_size,
            max_seen=settings.session_max_seen,
        )
        await sessions.save(session)

    return SearchResponse(
        query=body.query,
        session_id=session.id if session else None,
        context_applied=context_applied,
        hits=[SearchHit(**h) for h in hits],
        timings=Timings(
            embed_ms=_ms(start, embedded),
            search_ms=_ms(embedded, searched),
            total_ms=_ms(start, perf_counter()),
        ),
    )


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED, tags=["sessions"])
async def create_session(request: Request):
    _, _, _, sessions = _services(request)
    return _session_out(await sessions.create())


@router.get("/sessions/{session_id}", response_model=SessionOut, tags=["sessions"])
async def get_session(session_id: str, request: Request):
    _, _, _, sessions = _services(request)
    session = await sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found or expired")
    return _session_out(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["sessions"])
async def delete_session(session_id: str, request: Request):
    _, _, _, sessions = _services(request)
    if not await sessions.delete(session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found or expired")
