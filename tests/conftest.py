import hashlib
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sessions import InMemorySessionStore


class FakeEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors. No torch needed."""

    model_name = "fake-hash-embedder"
    dim = 256

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for word in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_query(self, text: str) -> np.ndarray:
        return self._vec(text)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts])


class FakeVectorStore:
    """Brute-force cosine search with the same filter semantics as ElasticVectorStore."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.last_search: dict | None = None

    async def ensure_index(self):
        pass

    async def index_documents(self, docs, vectors, refresh=False):
        ids = []
        for i, (doc, vec) in enumerate(zip(docs, vectors)):
            doc_id = doc.get("id") or f"auto-{len(self.docs) + i}"
            self.docs[doc_id] = {**doc, "id": doc_id, "vec": vec}
            ids.append(doc_id)
        return ids, 0

    async def delete(self, doc_id):
        return self.docs.pop(doc_id, None) is not None

    async def search(self, vector, k, num_candidates, filters=None, exclude_ids=None):
        self.last_search = {"vector": vector, "filters": filters, "exclude_ids": exclude_ids}
        excluded = set(exclude_ids or [])

        def matches(doc):
            for key, want in (filters or {}).items():
                have = doc.get("metadata", {}).get(key)
                if have not in (want if isinstance(want, list) else [want]):
                    return False
            return doc["id"] not in excluded

        scored = [
            ((1 + float(np.dot(vector, d["vec"]))) / 2, d)  # same scale as ES cosine scores
            for d in self.docs.values()
            if matches(d)
        ]
        scored.sort(key=lambda x: -x[0])
        return [
            {"id": d["id"], "score": s, "title": d.get("title"), "text": d["text"], "metadata": d.get("metadata", {})}
            for s, d in scored[:k]
        ]

    async def count(self):
        return len(self.docs)

    async def ping(self):
        return True


@pytest.fixture
def store():
    return FakeVectorStore()


@pytest.fixture
def client(store):
    settings = Settings(redis_url=None)
    app = create_app(settings, embedder=FakeEmbedder(), store=store, sessions=InMemorySessionStore(60))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(client):
    docs = [
        {"id": "py", "title": "Python", "text": "programming language code", "metadata": {"category": "tech"}},
        {"id": "rust", "title": "Rust", "text": "rust programming language memory safety", "metadata": {"category": "tech"}},
        {"id": "snake", "title": "Python", "text": "snake reptile jungle animal", "metadata": {"category": "nature"}},
        {"id": "tiger", "title": "Tigers", "text": "tiger jungle animal predator", "metadata": {"category": "nature"}},
    ]
    resp = client.post("/documents", json={"documents": docs})
    assert resp.status_code == 200
    return client
