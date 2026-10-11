from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden with a VF_-prefixed env var."""

    model_config = SettingsConfigDict(env_prefix="VF_", env_file=".env", extra="ignore")

    # Elasticsearch
    es_url: str = "http://localhost:9200"
    es_api_key: str | None = None
    es_index: str = "vectorflow-docs"
    es_timeout_seconds: float = 10.0
    es_startup_retries: int = 30

    # Redis (leave empty to fall back to an in-process session store)
    redis_url: str | None = "redis://localhost:6379/0"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 64
    query_prefix: str = ""  # e.g. "query: " for e5 models
    document_prefix: str = ""  # e.g. "passage: " for e5 models
    query_cache_size: int = 4096

    # kNN: num_candidates = k * factor (higher = better recall, slower)
    num_candidates_factor: int = 10

    # Sessions
    session_ttl_seconds: int = 1800
    session_context_weight: float = 0.3  # how much prior context steers the current query
    session_decay: float = 0.6  # how much old context survives each new query
    session_history_size: int = 20
    session_max_seen: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
