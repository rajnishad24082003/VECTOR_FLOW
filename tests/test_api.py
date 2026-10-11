def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "elasticsearch": True,
        "sessions": True,
        "model": "fake-hash-embedder",
        "documents": 0,
    }
    assert "X-Response-Time-Ms" in resp.headers


def test_index_and_search(seeded):
    resp = seeded.post("/search", json={"query": "jungle animal", "k": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert {h["id"] for h in body["hits"]} == {"snake", "tiger"}
    assert body["session_id"] is None
    assert body["context_applied"] is False
    assert set(body["timings"]) == {"embed_ms", "search_ms", "total_ms"}


def test_index_generates_ids(client):
    resp = client.post("/documents", json={"documents": [{"text": "hello"}, {"text": "world"}]})
    body = resp.json()
    assert body["indexed"] == 2 and body["failed"] == 0 and len(set(body["ids"])) == 2


def test_validation(client):
    assert client.post("/search", json={"query": ""}).status_code == 422
    assert client.post("/search", json={"query": "x", "k": 0}).status_code == 422
    assert client.post("/documents", json={"documents": []}).status_code == 422


def test_metadata_filters(seeded, store):
    resp = seeded.post("/search", json={"query": "python", "k": 5, "filters": {"category": "nature"}})
    assert [h["id"] for h in resp.json()["hits"]] == ["snake", "tiger"]
    assert store.last_search["filters"] == {"category": "nature"}

    resp = seeded.post("/search", json={"query": "python", "filters": {"category": ["tech", "nature"]}})
    assert len(resp.json()["hits"]) == 4


def test_delete_document(seeded):
    assert seeded.delete("/documents/py").status_code == 204
    assert seeded.delete("/documents/py").status_code == 404
    ids = [h["id"] for h in seeded.post("/search", json={"query": "python"}).json()["hits"]]
    assert "py" not in ids


def test_session_lifecycle(client):
    created = client.post("/sessions")
    assert created.status_code == 201
    sid = created.json()["id"]
    assert client.get(f"/sessions/{sid}").json()["queries"] == []
    assert client.delete(f"/sessions/{sid}").status_code == 204
    assert client.get(f"/sessions/{sid}").status_code == 404
    assert client.post("/search", json={"query": "x", "session_id": sid}).status_code == 404


def test_session_context_steers_ambiguous_query(seeded):
    """'python' is ambiguous; after talking about jungle animals the snake should win."""
    plain = seeded.post("/search", json={"query": "python", "k": 1}).json()
    assert plain["hits"][0]["id"] == "py"

    sid = seeded.post("/sessions").json()["id"]
    seeded.post("/search", json={"query": "jungle animal reptile", "session_id": sid})
    first = seeded.post("/search", json={"query": "python", "k": 1, "session_id": sid}).json()
    assert first["context_applied"] is True
    assert first["hits"][0]["id"] == "snake"

    no_ctx = seeded.post("/search", json={"query": "python", "k": 1, "session_id": sid, "use_context": False}).json()
    assert no_ctx["context_applied"] is False
    assert no_ctx["hits"][0]["id"] == "py"

    session = seeded.get(f"/sessions/{sid}").json()
    assert session["queries"] == ["jungle animal reptile", "python", "python"]
    assert session["has_context"] is True


def test_session_exclude_seen(seeded, store):
    sid = seeded.post("/sessions").json()["id"]
    first = seeded.post("/search", json={"query": "programming", "k": 2, "session_id": sid}).json()
    first_ids = {h["id"] for h in first["hits"]}

    second = seeded.post(
        "/search", json={"query": "programming", "k": 2, "session_id": sid, "exclude_seen": True}
    ).json()
    assert first_ids.isdisjoint(h["id"] for h in second["hits"])
    assert set(store.last_search["exclude_ids"]) == first_ids
    assert seeded.get(f"/sessions/{sid}").json()["seen_count"] == 4
