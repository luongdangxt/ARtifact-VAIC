# Chạy dự án bằng Docker (dùng GPU NVIDIA)

Cách này giúp bạn **không cài thư viện Python thẳng vào máy**. Mọi thư viện,
PyTorch, model embedding và vector DB đều nằm gọn trong Docker image / thư mục dự
án. Container sẽ chạy embedding trên **GPU NVIDIA** cho nhanh. Khi không cần nữa,
gỡ vài lệnh là sạch (xem mục *Dọn dẹp*).

## 0. Cài Docker + hỗ trợ GPU (chỉ làm một lần)

### 0.1. Đồng bộ hệ thống trước

Lỗi 404 khi cài gói là do database của pacman đã cũ (nó tìm phiên bản gói không
còn trên mirror). Đồng bộ + nâng cấp toàn bộ trước — **Arch không được cài gói
lẻ khi DB cũ**:

```bash
sudo pacman -Syu
```

> Nếu mirror Việt Nam vẫn lỗi/chậm, làm mới danh sách mirror rồi thử lại:
> ```bash
> sudo pacman -S reflector
> sudo reflector --country Vietnam,Singapore,Japan --age 12 --protocol https \
>     --sort rate --save /etc/pacman.d/mirrorlist
> sudo pacman -Syyu
> ```

### 0.2. Cài Docker

```bash
sudo pacman -S docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # để chạy docker không cần sudo
```

Sau lệnh `usermod`, **đăng xuất rồi đăng nhập lại** (hoặc khởi động lại) để có
hiệu lực.

### 0.3. Cài NVIDIA Container Toolkit (để Docker thấy GPU)

Driver NVIDIA bạn đã có sẵn (kiểm tra bằng `nvidia-smi`). Chỉ cần thêm cầu nối
cho Docker:

```bash
sudo pacman -S nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 0.4. Kiểm tra

```bash
docker --version
docker compose version
# Thử GPU trong container - phải in ra bảng nvidia-smi giống trên host:
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

## 1. Tạo file `.env`

```bash
cp .env.example .env
```

Mở `.env`, dán Gemini API key thật vào `GEMINI_API_KEY`
(lấy tại https://aistudio.google.com/apikey).

## 2. Build image

```bash
docker compose build
```

Lần đầu sẽ tải Python, PyTorch (bản CUDA cu124) và các thư viện — mất vài phút
và khá nặng (~vài GB) vì kèm thư viện CUDA.

## 3. Tạo Vector DB (chạy một lần)

```bash
docker compose run --rm chatbot python create_vectorDB.py --reset
```

Lần đầu sẽ tải model embedding `multilingual-e5-base` (~1 GB) về
`./.cache/huggingface`, rồi tạo index vào `./storage`. Chờ thanh tiến trình chạy
xong. Về sau nếu thêm PDF mới, chạy lại không có `--reset`.

## 4. Chạy chatbot

```bash
docker compose run --rm chatbot
```

Đây là chế độ hỏi đáp tương tác. Gõ `danhsach` để xem di sản, `thoat` để thoát.

Một số lệnh khác:

```bash
# Hỏi nhanh một câu rồi thoát
docker compose run --rm chatbot python run.py -q "Nhã nhạc cung đình là gì?"

# Liệt kê di sản
docker compose run --rm chatbot python run.py --list
```

> Dùng `docker compose run --rm` (không phải `up`) vì đây là app dòng lệnh tương
> tác; `--rm` tự xóa container sau khi thoát.

## 5. Dọn dẹp (xóa sạch)

Dữ liệu tạo ra (`./storage`, `./.cache`) nằm trong thư mục dự án nên **xóa thư
mục dự án là mất luôn**. Riêng Docker image nằm trong Docker, gỡ bằng:

```bash
# Xóa image của dự án + container còn sót
docker compose down --rmi local

# (Tùy chọn) dọn cache build không dùng tới của Docker
docker builder prune
```

Sau đó xóa thư mục dự án là không còn dấu vết gì trên máy.

## Ghi chú

- Chạy trên GPU nên tạo Vector DB nhanh. Kiểm tra GPU đang được dùng: khi
  `create_vectorDB.py` chạy, mở terminal khác gõ `nvidia-smi` sẽ thấy tiến trình
  `python`.
- GPU Quadro RTX 3000 chỉ có 6 GB VRAM. Model e5-base nhỏ nên thoải mái, nhưng
  nếu gặp lỗi hết VRAM khi tạo DB, giảm batch:
  `docker compose run --rm chatbot python create_vectorDB.py --batch-size 4 --reset`
- Muốn quay lại chạy CPU: đổi `RAG_EMBEDDING_DEVICE=cpu` trong `.env` (không cần
  build lại; bản torch cu124 vẫn chạy CPU được).
- `./.cache` và `./storage` được `.gitignore` bỏ qua, không lo commit nhầm.
- Nếu uid của bạn không phải `1000`, sửa dòng `user: "1000:1000"` trong
  `docker-compose.yml` cho khớp (`id -u` để xem).
