#!/usr/bin/env bash
# Chạy ĐỒNG THỜI backend AI (FastAPI :8000, trong Docker) + web-ar (Next :3000).
# Dùng: ./dev.sh           (Ctrl+C để tắt cả hai)
#       ./dev.sh --https    web-ar chạy HTTPS 0.0.0.0:3000 — cần cho camera AR
#                           khi test bằng điện thoại trong cùng LAN.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f docker-compose.api.yml)

WEB_SCRIPT=dev
WEB_URL="http://localhost:3000"
if [[ "${1:-}" == "--https" ]]; then
  WEB_SCRIPT=dev:https
  # In kèm IP LAN để quét bằng điện thoại — HTTPS là bắt buộc thì iOS mới mở camera.
  LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)"
  WEB_URL="https://localhost:3000${LAN_IP:+  |  https://$LAN_IP:3000}"
fi

_cleaned=0
cleanup() {
  [[ "$_cleaned" == 1 ]] && return
  _cleaned=1
  echo
  echo "Đang tắt cả hai server..."
  ( cd "$ROOT/Ai-backend" && "${COMPOSE[@]}" down --remove-orphans ) >/dev/null 2>&1 || true
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# heritage_ai/ được COPY vào image chứ không mount, nên code Python mới sửa chỉ
# vào được container sau khi build lại. Layer pip đã cache -> chỉ vài giây.
echo "▶ Build image backend..."
( cd "$ROOT/Ai-backend" && "${COMPOSE[@]}" build )

echo "▶ Backend AI  ->  http://localhost:5567  (health: /)"
( cd "$ROOT/Ai-backend" && exec "${COMPOSE[@]}" up --no-build ) &

# Chờ port 8000 mở, để web-ar không bị gọi vào backend chưa lên. Model embedding E5
# nạp tiếp ~15s trong thread warmup nền -> câu hỏi đầu tiên có thể chậm hơn vài giây.
printf "  chờ backend mở port"
for _ in $(seq 1 60); do
  if curl -sf -m 2 http://localhost:5567/ >/dev/null 2>&1; then
    echo " ✓"
    break
  fi
  printf .
  sleep 1
done

echo "▶ Web AR      ->  $WEB_URL"
( cd "$ROOT/web-ar" && exec npm run "$WEB_SCRIPT" ) &

wait
