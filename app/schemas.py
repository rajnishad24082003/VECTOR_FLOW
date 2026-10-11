from typing import Any, Union

from pydantic import BaseModel, Field

FilterValue = Union[str, int, float, bool, list[Union[str, int, float, bool]]]


class DocumentIn(BaseModel):
    id: str | None = Field(None, description="Optional; generated if omitted. Re-using an id overwrites.")
    title: str | None = None
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    documents: list[DocumentIn] = Field(..., min_length=1, max_length=1000)
    refresh: bool = Field(True, description="Make documents searchable before returning.")


class IndexResponse(BaseModel):
    indexed: int
    failed: int
    ids: list[str]
    took_ms: float


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    k: int = Field(10, ge=1, le=100)
    session_id: str | None = Field(None, description="Attach the query to a session for continuous context.")
    filters: dict[str, FilterValue] | None = Field(
        None, description='Exact-match metadata filters, e.g. {"category": "science"} or {"tag": ["a", "b"]}.'
    )
    use_context: bool = Field(True, description="Blend the session's context vector into this query.")
    exclude_seen: bool = Field(False, description="Skip documents already returned in this session.")


class SearchHit(BaseModel):
    id: str
    score: float
    title: str | None
    text: str
    metadata: dict[str, Any]


class Timings(BaseModel):
    embed_ms: float
    search_ms: float
    total_ms: float


class SearchResponse(BaseModel):
    query: str
    session_id: str | None
    context_applied: bool
    hits: list[SearchHit]
    timings: Timings


class SessionOut(BaseModel):
    id: str
    created_at: float
    updated_at: float
    queries: list[str]
    seen_count: int
    has_context: bool


class HealthResponse(BaseModel):
    status: str
    elasticsearch: bool
    sessions: bool
    model: str
    documents: int | None = None
