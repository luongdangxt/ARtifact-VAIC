#!/usr/bin/env bash
# Chạy ĐỒNG THỜI backend AI (FastAPI :8000) + web-ar (Next :3000).
# Dùng: ./dev.sh   (Ctrl+C để tắt cả hai)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() { echo; echo "Đang tắt cả hai server..."; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▶ Backend AI  ->  http://localhost:8000  (health: /health)"
( cd "$ROOT/Ai-backend" && exec .venv/bin/python scripts/run_api.py ) &

echo "▶ Web AR      ->  http://localhost:3000"
( cd "$ROOT/web-ar" && exec npm run dev ) &

wait
