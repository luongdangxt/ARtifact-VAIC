FROM python:3.11-slim

# Đặt biến môi trường
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết (bao gồm portaudio cho sounddevice)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Copy và cài đặt requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Mở port 5567
EXPOSE 5567

# Lệnh chạy server
CMD ["uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "5567"]
