import asyncio

import numpy as np

from app.sessions import InMemorySessionStore, Session, blend_query, record_query
from app.store import build_filter


def unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_blend_query():
    q, ctx = unit(1, 0), unit(0, 1)
    assert blend_query(q, None, 0.5) is q
    assert blend_query(q, ctx, 0.0) is q
    blended = blend_query(q, ctx, 0.5)
    np.testing.assert_allclose(blended, unit(1, 1), rtol=1e-6)
    assert abs(np.linalg.norm(blended) - 1) < 1e-6


def test_record_query_context_and_caps():
    s = Session.new()
    record_query(s, "a", unit(1, 0), ["d1", "d2"], decay=0.5, history_size=2, max_seen=3)
    np.testing.assert_allclose(s.context, unit(1, 0))
    record_query(s, "b", unit(0, 1), ["d2", "d3"], decay=0.5, history_size=2, max_seen=3)
    np.testing.assert_allclose(s.context, unit(1, 1), rtol=1e-6)
    record_query(s, "c", unit(0, 1), ["d4"], decay=0.5, history_size=2, max_seen=3)
    assert s.queries == ["b", "c"]
    assert s.seen_ids == ["d2", "d3", "d4"]  # ordered, deduped, oldest dropped


def test_session_roundtrip():
    s = Session.new()
    record_query(s, "q", unit(3, 4), ["x"], decay=0.5, history_size=5, max_seen=5)
    restored = Session.from_json(s.to_json())
    assert restored.id == s.id and restored.queries == ["q"] and restored.seen_ids == ["x"]
    np.testing.assert_array_equal(restored.context, s.context)
    assert Session.from_json(Session.new().to_json()).context is None


def test_in_memory_store_expiry():
    async def scenario():
        store = InMemorySessionStore(ttl_seconds=-1)  # already expired on save
        s = await store.create()
        assert await store.get(s.id) is None

        store = InMemorySessionStore(ttl_seconds=60)
        s = await store.create()
        assert (await store.get(s.id)).id == s.id
        assert await store.delete(s.id) is True
        assert await store.delete(s.id) is False

    asyncio.run(scenario())


def test_build_filter():
    f = build_filter({"category": "tech", "tags": ["a", 1], "active": True}, ["x"])
    assert f == {
        "bool": {
            "filter": [
                {"term": {"metadata.category": "tech"}},
                {"terms": {"metadata.tags": ["a", "1"]}},
                {"term": {"metadata.active": "true"}},
            ],
            "must_not": [{"ids": {"values": ["x"]}}],
        }
    }
    assert build_filter(None, None) == {"bool": {"filter": [], "must_not": []}}
