"""Bulk-load documents into VectorFlow through the HTTP API.

Examples:
    python scripts/ingest.py --jsonl data/sample_docs.jsonl
    python scripts/ingest.py --hf-dataset ag_news --text-field text --limit 20000   # needs `pip install datasets`

JSONL lines look like: {"id": "...", "title": "...", "text": "...", "metadata": {...}}
"""

import argparse
import json
import sys
import time
from collections.abc import Iterator

import httpx


def read_jsonl(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_hf(name: str, split: str, text_field: str, title_field: str | None, limit: int | None) -> Iterator[dict]:
    from datasets import load_dataset

    ds = load_dataset(name, split=split, streaming=True)
    for i, row in enumerate(ds):
        if limit is not None and i >= limit:
            break
        meta = {k: v for k, v in row.items() if k not in (text_field, title_field) and isinstance(v, (str, int, bool))}
        yield {
            "id": f"{name.replace('/', '_')}-{split}-{i}",
            "title": row.get(title_field) if title_field else None,
            "text": row[text_field],
            "metadata": meta,
        }


def batched(it: Iterator[dict], size: int) -> Iterator[list[dict]]:
    batch = []
    for item in it:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--jsonl")
    src.add_argument("--hf-dataset")
    p.add_argument("--split", default="train")
    p.add_argument("--text-field", default="text")
    p.add_argument("--title-field")
    p.add_argument("--limit", type=int)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--api", default="http://localhost:8000")
    args = p.parse_args()

    docs = (
        read_jsonl(args.jsonl)
        if args.jsonl
        else read_hf(args.hf_dataset, args.split, args.text_field, args.title_field, args.limit)
    )

    total = failed = 0
    start = time.perf_counter()
    with httpx.Client(base_url=args.api, timeout=300) as client:
        for batch in batched(docs, args.batch_size):
            # refresh=False keeps bulk loads fast; ES makes docs searchable within refresh_interval (1s).
            resp = client.post("/documents", json={"documents": batch, "refresh": False})
            resp.raise_for_status()
            body = resp.json()
            total += body["indexed"]
            failed += body["failed"]
            rate = total / (time.perf_counter() - start)
            print(f"\rindexed {total} docs ({failed} failed) - {rate:.0f} docs/s", end="", flush=True)
    print(f"\ndone in {time.perf_counter() - start:.1f}s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
