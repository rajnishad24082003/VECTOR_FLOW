"""Measure /search latency under concurrent load.

    python scripts/benchmark.py --requests 1000 --concurrency 16

Reports client-observed latency and the server's own breakdown (embedding vs Elasticsearch).
Queries are made unique by default (--allow-cache to disable) so the embedding cache doesn't
flatter the numbers.
"""

import argparse
import asyncio
import random
import statistics
import time

import httpx

BASE_QUERIES = [
    "how do vaccines train the immune system",
    "best practices for scaling a web service",
    "causes of inflation and interest rates",
    "training neural networks on small datasets",
    "climate change effects on ocean ecosystems",
    "how does a transformer language model work",
    "symptoms of vitamin deficiency",
    "renewable energy storage with batteries",
    "history of space exploration missions",
    "football transfer market records",
    "database indexing for fast lookups",
    "remote work productivity tips",
]
SUFFIXES = ["", "explained", "overview", "in simple terms", "latest research", "examples", "pros and cons", "guide"]


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


async def run(args) -> None:
    client_ms: list[float] = []
    server: dict[str, list[float]] = {"embed_ms": [], "search_ms": [], "total_ms": []}
    errors = 0
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.api, timeout=30) as client:
        session_id = None
        if args.session:
            session_id = (await client.post("/sessions")).json()["id"]

        async def one(i: int) -> None:
            nonlocal errors
            query = random.choice(BASE_QUERIES)
            if not args.allow_cache:
                query = f"{query} {random.choice(SUFFIXES)} {i}"
            async with sem:
                start = time.perf_counter()
                resp = await client.post("/search", json={"query": query, "k": args.k, "session_id": session_id})
                elapsed = (time.perf_counter() - start) * 1000
            if resp.status_code != 200:
                errors += 1
                return
            client_ms.append(elapsed)
            for key, val in resp.json()["timings"].items():
                server[key].append(val)

        for i in range(args.warmup):
            await one(-i - 1)
        client_ms.clear()
        for v in server.values():
            v.clear()

        wall = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(args.requests)))
        wall = time.perf_counter() - wall

    print(f"requests={args.requests} concurrency={args.concurrency} k={args.k} errors={errors}")
    print(f"throughput: {len(client_ms) / wall:.1f} req/s\n")
    print(f"{'metric':<18}{'p50':>9}{'p95':>9}{'p99':>9}{'mean':>9}")
    rows = [("client latency", client_ms)] + [(f"server {k}", v) for k, v in server.items()]
    for name, vals in rows:
        if vals:
            print(
                f"{name:<18}{pct(vals, 50):>9.1f}{pct(vals, 95):>9.1f}{pct(vals, 99):>9.1f}"
                f"{statistics.mean(vals):>9.1f}"
            )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--requests", type=int, default=500)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--warmup", type=int, default=20)
    p.add_argument("--session", action="store_true", help="Run all queries inside one session")
    p.add_argument("--allow-cache", action="store_true", help="Repeat identical queries (hits embedding cache)")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
