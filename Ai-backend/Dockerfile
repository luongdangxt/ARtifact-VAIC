# Image chạy chatbot RAG di sản (CPU-only, gọn nhẹ)
FROM python:3.11-slim

# Không ghi file .pyc, log ra ngay lập tức, UTF-8 cho tiếng Việt
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Cài PyTorch bản CUDA (cu124) trước - wheel này tự kèm thư viện CUDA runtime,
# nên chỉ cần driver NVIDIA trên host (qua nvidia-container-toolkit), không cần
# image CUDA base. Rồi mới cài các thư viện còn lại.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cu124 \
    && pip install -r requirements.txt

# Copy source code (dataset/storage/.env sẽ được mount lúc chạy)
COPY heritage_ai/ ./heritage_ai/
COPY run.py create_vectorDB.py ./

CMD ["python", "run.py"]
