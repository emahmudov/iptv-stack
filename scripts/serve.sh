#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${1:-8080}"
PYTHONPATH=src python3 -m iptv_stack serve --root "$ROOT_DIR" --port "$PORT"
