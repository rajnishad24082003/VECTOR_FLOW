import logging
from contextlib import AsyncExitStack, asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api import router
from app.config import Settings, get_settings
from app.embeddings import Embedder, HFEmbedder
from app.sessions import InMemorySessionStore, RedisSessionStore, SessionStore
from app.store import ElasticVectorStore, VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vectorflow")


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
    sessions: SessionStore | None = None,
) -> FastAPI:
    """Build the app. Components can be injected (used by tests); otherwise they're built from settings."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as cleanup:
            emb = embedder
            if emb is None:
                logger.info("Loading embedding model %s", settings.embedding_model)
                emb = await run_in_threadpool(
                    HFEmbedder,
                    settings.embedding_model,
                    device=settings.embedding_device,
                    batch_size=settings.embedding_batch_size,
                    query_prefix=settings.query_prefix,
                    document_prefix=settings.document_prefix,
                    cache_size=settings.query_cache_size,
                )

            vs = store
            if vs is None:
                from elasticsearch import AsyncElasticsearch

                es_client = AsyncElasticsearch(
                    settings.es_url, api_key=settings.es_api_key, request_timeout=settings.es_timeout_seconds
                )
                cleanup.push_async_callback(es_client.close)
                vs = ElasticVectorStore(es_client, settings.es_index, emb.dim)
                await vs.wait_until_ready(retries=settings.es_startup_retries)
            await vs.ensure_index()

            ss = sessions
            if ss is None:
                if settings.redis_url:
                    ss = RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)
                else:
                    logger.warning("VF_REDIS_URL not set; using in-memory sessions (single worker only)")
                    ss = InMemorySessionStore(settings.session_ttl_seconds)
            cleanup.push_async_callback(ss.close)

            # Warm up so the first real request doesn't pay for lazy initialisation.
            await run_in_threadpool(emb.embed_documents, ["warm up"])

            app.state.settings = settings
            app.state.embedder = emb
            app.state.store = vs
            app.state.sessions = ss
            logger.info("VectorFlow ready (model=%s, dim=%d)", emb.model_name, emb.dim)
            yield

    app = FastAPI(
        title="VectorFlow",
        description="Semantic search API: Hugging Face embeddings + Elasticsearch kNN, with stateful sessions.",
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def response_time_header(request: Request, call_next):
        start = perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time-Ms"] = f"{(perf_counter() - start) * 1000:.2f}"
        return response

    app.include_router(router)
    return app


app = create_app()
