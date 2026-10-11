---
title: VectorFlow
emoji: 🔎
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
base_path: /docs
pinned: false
short_description: Semantic search with MiniLM, Elasticsearch kNN, sessions
---

# VectorFlow

Semantic search API: Hugging Face sentence-transformers (MiniLM) embeddings, Elasticsearch kNN (int8 HNSW), and stateful sessions that carry query context from one search to the next.

The page above is the interactive API docs. Try `POST /search` with:

```json
{"query": "how do I protect my money from rising prices", "k": 5}
```

To use sessions, call `POST /sessions`, then pass the returned `id` as `session_id` on each search.

The index is seeded with a small sample corpus on startup. This Space is a shared demo: anything you add is visible to everyone, and it's reset whenever the Space restarts.
