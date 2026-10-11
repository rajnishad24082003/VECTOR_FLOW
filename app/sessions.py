"""Stateful search sessions.

A session remembers recent queries, which documents were already returned, and a
"context vector": an exponentially decaying average of past query embeddings. Each
new query is blended with that context, so a follow-up like "what about pricing?"
is steered towards the topic the user has been exploring.
"""

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v if norm == 0 else (v / norm).astype(np.float32)


@dataclass
class Session:
    id: str
    created_at: float
    updated_at: float
    queries: list[str] = field(default_factory=list)
    seen_ids: list[str] = field(default_factory=list)
    context: np.ndarray | None = None

    @classmethod
    def new(cls) -> "Session":
        now = time.time()
        return cls(id=uuid.uuid4().hex, created_at=now, updated_at=now)

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "queries": self.queries,
                "seen_ids": self.seen_ids,
                "context": None
                if self.context is None
                else base64.b64encode(self.context.astype(np.float32).tobytes()).decode(),
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Session":
        data = json.loads(raw)
        ctx = data.pop("context")
        context = None if ctx is None else np.frombuffer(base64.b64decode(ctx), dtype=np.float32).copy()
        return cls(**data, context=context)


def blend_query(query_vec: np.ndarray, context: np.ndarray | None, weight: float) -> np.ndarray:
    """Steer the query towards the session context. weight=0 ignores context entirely."""
    if context is None or weight <= 0:
        return query_vec
    return _normalize((1 - weight) * query_vec + weight * context)


def record_query(
    session: Session,
    query: str,
    query_vec: np.ndarray,
    result_ids: list[str],
    decay: float,
    history_size: int,
    max_seen: int,
) -> None:
    """Fold a completed query and its results into the session (in place)."""
    session.context = (
        query_vec.astype(np.float32).copy()
        if session.context is None
        else _normalize(decay * session.context + (1 - decay) * query_vec)
    )
    session.queries = (session.queries + [query])[-history_size:]
    seen = dict.fromkeys(session.seen_ids)  # ordered set
    for doc_id in result_ids:
        seen.pop(doc_id, None)
        seen[doc_id] = None
    session.seen_ids = list(seen)[-max_seen:]
    session.updated_at = time.time()


class SessionStore(Protocol):
    async def create(self) -> Session: ...

    async def get(self, session_id: str) -> Session | None: ...

    async def save(self, session: Session) -> None: ...

    async def delete(self, session_id: str) -> bool: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class InMemorySessionStore:
    """Single-process fallback; sessions are lost on restart and not shared across workers."""

    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._data: dict[str, tuple[float, str]] = {}

    async def create(self) -> Session:
        session = Session.new()
        await self.save(session)
        return session

    async def get(self, session_id: str) -> Session | None:
        entry = self._data.get(session_id)
        if entry is None:
            return None
        expires_at, raw = entry
        if expires_at < time.time():
            del self._data[session_id]
            return None
        return Session.from_json(raw)

    async def save(self, session: Session) -> None:
        self._data[session.id] = (time.time() + self.ttl, session.to_json())

    async def delete(self, session_id: str) -> bool:
        return self._data.pop(session_id, None) is not None

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class RedisSessionStore:
    """Sessions stored as JSON with a sliding TTL (refreshed on every save)."""

    def __init__(self, url: str, ttl_seconds: int, prefix: str = "vf:session:"):
        import redis.asyncio as redis

        self._redis = redis.from_url(url)
        self.ttl = ttl_seconds
        self.prefix = prefix

    def _key(self, session_id: str) -> str:
        return self.prefix + session_id

    async def create(self) -> Session:
        session = Session.new()
        await self.save(session)
        return session

    async def get(self, session_id: str) -> Session | None:
        raw = await self._redis.get(self._key(session_id))
        return None if raw is None else Session.from_json(raw)

    async def save(self, session: Session) -> None:
        await self._redis.set(self._key(session.id), session.to_json(), ex=self.ttl)

    async def delete(self, session_id: str) -> bool:
        return bool(await self._redis.delete(self._key(session_id)))

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self._redis.aclose()
