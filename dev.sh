#!/usr/bin/env bash
# Chạy ĐỒNG THỜI backend AI (FastAPI :5567, trong Docker) + web-ar (Next :3000).
# Dùng: ./dev.sh            (Ctrl+C để tắt tất cả)
#       ./dev.sh --https     web-ar chạy HTTPS 0.0.0.0:3000 — cần cho camera AR
#                            khi test bằng điện thoại trong cùng LAN.
#       ./dev.sh --tunnel    mở thêm Cloudflare quick tunnel -> link https công khai
#                            (*.trycloudflare.com), test bằng 4G không cần chung wifi.
#       Ghép được: ./dev.sh --https --tunnel
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f docker-compose.api.yml)

USE_HTTPS=0
USE_TUNNEL=0
for arg in "$@"; do
  case "$arg" in
    --https)  USE_HTTPS=1 ;;
    --tunnel) USE_TUNNEL=1 ;;
    *) echo "Tham số lạ: $arg  (chỉ nhận --https, --tunnel)" >&2; exit 1 ;;
  esac
done

WEB_SCRIPT=dev
WEB_URL="http://localhost:3000"
if [[ "$USE_HTTPS" == 1 ]]; then
  WEB_SCRIPT=dev:https
  # In kèm IP LAN để quét bằng điện thoại — HTTPS là bắt buộc thì iOS mới mở camera.
  LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)"
  WEB_URL="https://localhost:3000${LAN_IP:+  |  https://$LAN_IP:3000}"
fi

if [[ "$USE_TUNNEL" == 1 ]] && ! command -v cloudflared >/dev/null 2>&1; then
  echo "Không tìm thấy cloudflared trong PATH — cài rồi chạy lại (--tunnel)." >&2
  exit 1
fi
CF_LOG=""

_cleaned=0
cleanup() {
  [[ "$_cleaned" == 1 ]] && return
  _cleaned=1
  echo
  echo "Đang tắt các server..."
  ( cd "$ROOT/Ai-backend" && "${COMPOSE[@]}" down --remove-orphans ) >/dev/null 2>&1 || true
  if [[ -n "$CF_LOG" ]]; then rm -f "$CF_LOG"; fi
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

if [[ "$USE_TUNNEL" == 1 ]]; then
  # Chờ Next mở port trước, không thì cú truy cập đầu qua tunnel ăn 502.
  # -k vì chế độ --https dùng cert tự ký.
  printf "  chờ web-ar mở port"
  for _ in $(seq 1 90); do
    if curl -skf -m 2 -o /dev/null "${WEB_URL%% *}/" 2>/dev/null; then
      echo " ✓"
      break
    fi
    printf .
    sleep 1
  done

  # Quick tunnel: KHÔNG cần đăng nhập Cloudflare, đổi tên miền mỗi lần chạy.
  # Cert tự ký của `next dev --experimental-https` -> phải --no-tls-verify.
  CF_ORIGIN="http://localhost:3000"
  CF_ARGS=()
  if [[ "$USE_HTTPS" == 1 ]]; then
    CF_ORIGIN="https://localhost:3000"
    CF_ARGS=(--no-tls-verify)
  fi
  CF_LOG="$(mktemp -t cloudflared-XXXXXX.log)"
  cloudflared tunnel --url "$CF_ORIGIN" "${CF_ARGS[@]}" >"$CF_LOG" 2>&1 &

  printf "  chờ Cloudflare cấp tên miền"
  CF_URL=""
  for _ in $(seq 1 40); do
    CF_URL="$(grep -om1 'https://[a-z0-9-]*\.trycloudflare\.com' "$CF_LOG" || true)"
    if [[ -n "$CF_URL" ]]; then break; fi
    printf .
    sleep 1
  done
  if [[ -n "$CF_URL" ]]; then
    echo " ✓"
    echo "▶ CÔNG KHAI   ->  $CF_URL"
    echo "  (HTTPS thật -> camera AR chạy trên 4G; link ĐỔI mỗi lần khởi động lại)"
  else
    echo " ✗"
    echo "  Cloudflare chưa trả tên miền. Log: $CF_LOG" >&2
  fi
fi

wait
