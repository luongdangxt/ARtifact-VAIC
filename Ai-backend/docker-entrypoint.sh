#!/bin/sh
# Ingest tự động rồi mới mở API.
#
# Vì sao cần: runtime chỉ đọc ChromaDB trong /app/storage, mà storage/ bị
# gitignore nên server clone về là rỗng. Không có bước này thì `up -d --build`
# dựng ra một API chạy ngon lành nhưng trả lời "chưa có tư liệu" cho mọi câu
# hỏi - kể cả 17 di sản đã có tư liệu sẵn trong image.
#
# Chạy lại vô hại: ingest so id chunk và bỏ qua phần đã có, nên chỉ lần đầu mới
# tốn thời gian (cộng thêm ~1.1GB tải model embedding về /app/.cache).
set -e

if [ "${AUTO_INGEST:-1}" = "1" ]; then
    if python - <<'PY'
import sys

from heritage_ai.rag.vector_store import ChromaVectorStore

try:
    # allow_embedding_mismatch: chỉ đếm, không cần khớp model embedding.
    count = ChromaVectorStore(
        "/app/storage/chroma", allow_embedding_mismatch=True
    ).count()
except Exception as exc:  # collection chưa tồn tại, file hỏng, quyền ghi...
    print(f"[entrypoint] Không đọc được VectorDB ({exc}), coi như rỗng.")
    count = 0
else:
    print(f"[entrypoint] VectorDB hiện có {count} chunk.")

sys.exit(0 if count > 0 else 1)
PY
    then
        echo "[entrypoint] Bỏ qua ingest."
    else
        # Mặc định --no-dataset: chỉ nạp heritage_ai/data/documents/ (17 di sản
        # tư liệu thật) + heritages.json. 485 PDF trong dataset/ là bản mô tả
        # mẫu một trang, ingest vào chỉ tổ cạnh tranh chỗ trong top_k; mount
        # ./dataset vẫn cần cho catalog tên di sản nên không mất gì.
        echo "[entrypoint] Ingest: create_vectorDB.py ${INGEST_ARGS:---no-dataset}"
        # shellcheck disable=SC2086
        python create_vectorDB.py ${INGEST_ARGS:---no-dataset}
    fi
fi

exec "$@"
