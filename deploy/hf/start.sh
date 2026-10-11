#!/usr/bin/env bash
# Runs Elasticsearch and the API in one container, then seeds the sample docs.
# Space storage is ephemeral, so the index starts empty on every boot.
set -euo pipefail

/usr/share/elasticsearch/bin/elasticsearch &
es_pid=$!

# The API waits for ES itself (VF_ES_STARTUP_RETRIES).
uvicorn app.main:app --host 0.0.0.0 --port 7860 &
api_pid=$!

trap 'kill "$es_pid" "$api_pid" 2>/dev/null' TERM INT

(
    python - <<'EOF'
import time, urllib.request

for _ in range(300):
    try:
        urllib.request.urlopen("http://127.0.0.1:7860/health", timeout=4)
        break
    except Exception:
        time.sleep(1)
EOF
    python scripts/ingest.py --jsonl data/sample_docs.jsonl --api http://127.0.0.1:7860 \
        || echo "WARNING: seeding sample docs failed" >&2
) &

# If either server dies, exit so the Space restarts the container.
wait -n "$es_pid" "$api_pid"
status=$?
kill "$es_pid" "$api_pid" 2>/dev/null || true
exit "$status"
