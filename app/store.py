import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

import numpy as np
from elasticsearch import AsyncElasticsearch, BadRequestError
from elasticsearch import ConnectionError as ESConnectionError
from elasticsearch.helpers import async_bulk

logger = logging.getLogger(__name__)

Filters = dict[str, Any]


class VectorStore(Protocol):
    async def ensure_index(self) -> None: ...

    async def index_documents(
        self, docs: list[dict], vectors: np.ndarray, refresh: bool = False
    ) -> tuple[list[str], int]: ...

    async def delete(self, doc_id: str) -> bool: ...

    async def search(
        self,
        vector: np.ndarray,
        k: int,
        num_candidates: int,
        filters: Filters | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[dict]: ...

    async def count(self) -> int: ...

    async def ping(self) -> bool: ...


def _as_keyword(value: Any) -> str:
    # `flattened` fields index every leaf as a keyword string; JSON booleans become "true"/"false".
    return str(value).lower() if isinstance(value, bool) else str(value)


def build_filter(filters: Filters | None, exclude_ids: list[str] | None) -> dict:
    clauses = []
    for key, value in (filters or {}).items():
        if isinstance(value, list):
            clauses.append({"terms": {f"metadata.{key}": [_as_keyword(v) for v in value]}})
        else:
            clauses.append({"term": {f"metadata.{key}": _as_keyword(value)}})
    must_not = [{"ids": {"values": exclude_ids}}] if exclude_ids else []
    return {"bool": {"filter": clauses, "must_not": must_not}}


class ElasticVectorStore:
    def __init__(self, client: AsyncElasticsearch, index: str, dim: int):
        self.client = client
        self.index = index
        self.dim = dim

    async def wait_until_ready(self, retries: int = 30, delay: float = 2.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                await self.client.cluster.health(wait_for_status="yellow", timeout="5s")
                return
            except ESConnectionError:
                logger.info("Waiting for Elasticsearch (%d/%d)...", attempt, retries)
                await asyncio.sleep(delay)
        raise RuntimeError("Elasticsearch did not become available")

    async def ensure_index(self) -> None:
        if not await self.client.indices.exists(index=self.index):
            await self._create_index()
        mapping = await self.client.indices.get_mapping(index=self.index)
        props = next(iter(mapping.values()))["mappings"]["properties"]
        existing_dim = props["embedding"]["dims"]
        if existing_dim != self.dim:
            raise RuntimeError(
                f"Index '{self.index}' has {existing_dim}-dim vectors but the model produces "
                f"{self.dim}. Use a different VF_ES_INDEX or delete the index."
            )
        await self.client.cluster.health(index=self.index, wait_for_status="yellow", timeout="30s")

    async def _create_index(self) -> None:
        try:
            await self.client.indices.create(
                index=self.index,
                settings={"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "1s"},
                mappings={
                    "properties": {
                        "title": {"type": "text"},
                        "text": {"type": "text"},
                        "metadata": {"type": "flattened"},
                        "created_at": {"type": "date"},
                        "embedding": {
                            "type": "dense_vector",
                            "dims": self.dim,
                            "index": True,
                            "similarity": "cosine",
                            # int8 quantised HNSW: ~4x less memory, faster search, negligible recall loss
                            "index_options": {"type": "int8_hnsw", "m": 16, "ef_construction": 100},
                        },
                    }
                },
            )
            logger.info("Created index %s (dim=%d)", self.index, self.dim)
        except BadRequestError as e:
            # Another worker won the race to create it.
            if e.error != "resource_already_exists_exception":
                raise

    async def index_documents(
        self, docs: list[dict], vectors: np.ndarray, refresh: bool = False
    ) -> tuple[list[str], int]:
        now = datetime.now(timezone.utc).isoformat()
        ids = [d.get("id") or uuid.uuid4().hex for d in docs]
        actions = [
            {
                "_index": self.index,
                "_id": doc_id,
                "_source": {
                    "title": doc.get("title"),
                    "text": doc["text"],
                    "metadata": doc.get("metadata") or {},
                    "created_at": now,
                    "embedding": vec.tolist(),
                },
            }
            for doc_id, doc, vec in zip(ids, docs, vectors)
        ]
        ok, errors = await async_bulk(
            self.client, actions, refresh="wait_for" if refresh else False, raise_on_error=False
        )
        failed_ids = {next(iter(e.values())).get("_id") for e in errors}
        if errors:
            logger.warning("%d documents failed to index: %s", len(errors), errors[:3])
        return [i for i in ids if i not in failed_ids], len(errors)

    async def delete(self, doc_id: str) -> bool:
        resp = await self.client.delete(index=self.index, id=doc_id, refresh="wait_for", ignore_status=404)
        return resp.get("result") == "deleted"

    async def search(
        self,
        vector: np.ndarray,
        k: int,
        num_candidates: int,
        filters: Filters | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[dict]:
        resp = await self.client.search(
            index=self.index,
            knn={
                "field": "embedding",
                "query_vector": vector.tolist(),
                "k": k,
                "num_candidates": max(num_candidates, k),
                "filter": build_filter(filters, exclude_ids),
            },
            size=k,
            source_excludes=["embedding"],
        )
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "title": hit["_source"].get("title"),
                "text": hit["_source"].get("text", ""),
                "metadata": hit["_source"].get("metadata") or {},
            }
            for hit in resp["hits"]["hits"]
        ]

    async def count(self) -> int:
        resp = await self.client.count(index=self.index)
        return resp["count"]

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False
