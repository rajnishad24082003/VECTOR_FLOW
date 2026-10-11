#!/usr/bin/env bash
# Assemble a Hugging Face Docker Space repo from this project.
# Usage: deploy/hf/build_space.sh <space-repo-dir>   (e.g. a clone of https://huggingface.co/spaces/<user>/vectorflow)
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <space-repo-dir>" >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="$1"
mkdir -p "$out"

# Replace only what we own, so the target's .git and .gitattributes are left alone.
rm -rf "$out/app" "$out/scripts" "$out/data"
mkdir -p "$out/scripts" "$out/data"

cp "$here/Dockerfile" "$here/README.md" "$here/start.sh" "$here/elasticsearch.yml" "$out/"
cp "$root/requirements.txt" "$out/"
cp -r "$root/app" "$out/app"
cp "$root/scripts/ingest.py" "$out/scripts/"
cp "$root/data/sample_docs.jsonl" "$out/data/"
find "$out/app" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "Space repo assembled in $out"
