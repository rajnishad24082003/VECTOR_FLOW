import threading
from concurrent.futures import Future
from functools import lru_cache
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    dim: int
    model_name: str

    def embed_query(self, text: str) -> np.ndarray: ...

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...


class HFEmbedder:
    """Sentence-transformers model with an LRU cache in front of query encoding.

    All vectors are L2-normalised float32, so cosine similarity == dot product.
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        batch_size: int = 64,
        query_prefix: str = "",
        document_prefix: str = "",
        cache_size: int = 4096,
    ):
        # Imported lazily so the rest of the app (and tests) don't need torch.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device=device)
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())
        self._batch_size = batch_size
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        # torch already parallelises one forward pass across OMP_NUM_THREADS cores; running several
        # passes at once just makes them fight for the same cores, so the model is used under a lock.
        self._model_lock = threading.Lock()
        self._pending: list[tuple[str, Future]] = []
        self._pending_lock = threading.Lock()
        self._cached_query = lru_cache(maxsize=cache_size)(self._encode_query)

    def _run_model(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

    def _encode(self, texts: list[str]) -> np.ndarray:
        with self._model_lock:
            return self._run_model(texts)

    def _encode_query(self, text: str) -> np.ndarray:
        # Micro-batching: whichever thread gets the model lock encodes every query queued so far in a
        # single forward pass, which costs about the same as encoding one. Under concurrent load this
        # turns N sequential passes into ~1.
        future: Future = Future()
        with self._pending_lock:
            self._pending.append((self._query_prefix + text, future))
        with self._model_lock:
            if not future.done():
                with self._pending_lock:
                    batch, self._pending = self._pending, []
                try:
                    vectors = self._run_model([t for t, _ in batch])
                    for (_, f), vec in zip(batch, vectors):
                        vec.setflags(write=False)  # shared via the cache, so must not be mutated
                        f.set_result(vec)
                except BaseException as e:
                    for _, f in batch:
                        f.set_exception(e)
        return future.result()

    def embed_query(self, text: str) -> np.ndarray:
        return self._cached_query(text)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        # Encode one batch per lock acquisition so queries can interleave with bulk ingestion.
        texts = [self._document_prefix + t for t in texts]
        return np.concatenate(
            [self._encode(texts[i : i + self._batch_size]) for i in range(0, len(texts), self._batch_size)]
        )

    def cache_info(self) -> dict:
        info = self._cached_query.cache_info()
        return {"hits": info.hits, "misses": info.misses, "size": info.currsize}
