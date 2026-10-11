import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import numpy as np
import pytest

from app.embeddings import HFEmbedder


class SlowModel:
    """Stand-in for SentenceTransformer: maps each text to a one-hot of its length, records batch sizes."""

    def __init__(self, fail_on: str | None = None):
        self.batches: list[int] = []
        self.fail_on = fail_on

    def encode(self, texts, **_):
        time.sleep(0.05)
        if self.fail_on in texts:
            raise ValueError("boom")
        self.batches.append(len(texts))
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            out[i, len(t)] = 1
        return out


def make_embedder(model) -> HFEmbedder:
    emb = HFEmbedder.__new__(HFEmbedder)  # skip loading a real model
    emb.model_name, emb.dim, emb._model = "slow", 64, model
    emb._batch_size, emb._query_prefix, emb._document_prefix = 4, "", ""
    emb._model_lock, emb._pending_lock, emb._pending = threading.Lock(), threading.Lock(), []
    emb._cached_query = lru_cache(maxsize=16)(emb._encode_query)
    return emb


def test_concurrent_queries_are_micro_batched_and_routed_correctly():
    model = SlowModel()
    emb = make_embedder(model)
    texts = ["a" * n for n in range(1, 17)]
    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(emb.embed_query, texts))
    for text, vec in zip(texts, results):
        assert vec.argmax() == len(text)  # each caller got its own vector
        assert not vec.flags.writeable
    assert sum(model.batches) == 16
    assert len(model.batches) < 16  # queries were coalesced


def test_query_cache():
    model = SlowModel()
    emb = make_embedder(model)
    emb.embed_query("hello")
    emb.embed_query("hello")
    assert model.batches == [1]


def test_batch_failure_propagates_to_every_waiter():
    emb = make_embedder(SlowModel(fail_on="bad"))
    with ThreadPoolExecutor(2) as pool:
        bad = pool.submit(emb.embed_query, "bad")
        with pytest.raises(ValueError):
            bad.result()
    assert emb.embed_query("fine").argmax() == 4  # embedder still usable afterwards


def test_embed_documents_chunks():
    model = SlowModel()
    emb = make_embedder(model)
    out = emb.embed_documents(["x" * n for n in range(1, 11)])
    assert out.shape == (10, 64)
    assert model.batches == [4, 4, 2]
