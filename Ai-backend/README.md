# Nghệ nhân AI — Chatbot RAG về di sản văn hóa phi vật thể

Ứng dụng Python dạng văn bản giúp du khách tìm hiểu di sản văn hóa phi vật thể
Việt Nam. Hệ thống dùng:

- `intfloat/multilingual-e5-base` chạy local để tạo embedding tiếng Việt.
- ChromaDB chạy local để lưu và tìm kiếm vector.
- Gemini để nhận diện ý định câu hỏi và tạo lời kể từ tư liệu RAG.
- PDF trong thư mục `dataset` làm nguồn dữ liệu chính.

Ứng dụng không có phần voice. Hai file chạy chính được tách riêng:

- `create_vectorDB.py`: tạo hoặc cập nhật VectorDB.
- `run.py`: chạy chatbot sau khi VectorDB đã sẵn sàng.


## 1. Kiến trúc hệ thống

Luồng tạo VectorDB:

```text
PDF/JSON/TXT/Markdown
        ↓
Document Loader
        ↓
Text Chunker
        ↓
Multilingual E5 chạy local
        ↓
ChromaDB tại storage/chroma
```

Luồng hỏi đáp:

```text
Câu hỏi của du khách
        ↓
Local E5 tìm ứng viên di sản
        ↓
Gemini Semantic Router
        ↓
ChromaDB truy xuất tư liệu liên quan
        ↓
Research/Verification Agents
        ↓
Gemini tạo lời kể có mã trích dẫn
        ↓
Câu trả lời văn bản + nguồn tham khảo
```

## 2. Cấu trúc thư mục

```text
Chatbot_DeepSearch/
├── create_vectorDB.py           # Tạo/cập nhật VectorDB
├── run.py                       # Chạy chatbot
├── requirements.txt             # Thư viện Python
├── .env                         # API key và cấu hình local, không commit Git
├── dataset/
│   └── di_san_van_hoa_phi_vat_the_485_files_pdf/
│       └── *.pdf                # Dataset PDF chính
├── heritage_ai/
│   ├── orchestrator.py          # Điều phối pipeline hỏi đáp
│   ├── gemini_client.py         # Gemini API, Structured Output và retry
│   ├── query_processing.py      # Semantic Router và Reflection
│   ├── research_agents.py       # Các agent nghiên cứu/kiểm chứng
│   ├── report_agent.py          # Ghép câu trả lời và nguồn trích dẫn
│   ├── repository.py            # Catalog di sản
│   ├── dataset_catalog.py       # Tạo catalog tự động từ tên PDF
│   ├── models.py                # Kiểu dữ liệu dùng chung
│   ├── text_utils.py            # Chuẩn hóa tiếng Việt
│   ├── data/
│   │   ├── heritages.json       # Dữ liệu khởi tạo, alias và nguồn
│   │   └── documents/           # Tài liệu bổ sung
│   └── rag/
│       ├── document_loader.py   # Đọc PDF, TXT, Markdown và JSON
│       ├── text_chunker.py      # Chia tài liệu thành chunk
│       ├── embedding_client.py  # Multilingual E5 local
│       ├── vector_store.py      # ChromaDB local
│       ├── retriever.py         # Semantic retrieval
│       └── ingest.py            # Pipeline ingest dùng bởi create_vectorDB.py
├── storage/
│   └── chroma/                  # VectorDB sinh tự động, không commit Git
└── tests/
    ├── test_chatbot.py
    └── test_rag.py
```

## 3. Yêu cầu hệ thống

- Linux, macOS hoặc Windows có terminal.
- Python 3.10 trở lên; khuyến nghị Python 3.10 hoặc 3.11.
- Nên có 5–10 GB dung lượng trống; mức thực tế phụ thuộc bản PyTorch CPU/CUDA.
- Kết nối Internet ở lần đầu để cài thư viện và tải model.
- Gemini API key để phân tích câu hỏi và sinh câu trả lời.
- GPU NVIDIA là tùy chọn. CPU vẫn chạy được nhưng tạo VectorDB chậm hơn.

Dataset hiện tại có 485 file PDF, dung lượng khoảng 40 MB. VectorDB được lưu cục
bộ nên không cần gọi Gemini Embedding và không gặp quota embedding.

## 4. Tải source code

```bash
git clone https://github.com/PhamVanHung412004/Chatbot_DeepSearch.git
cd Chatbot_DeepSearch
```

Nếu source code đã có sẵn, chỉ cần đi vào thư mục dự án:

```bash
cd ~/PhamVanHung/Project_Github/Chatbot_DeepSearch
```

## 5. Tạo môi trường Conda

Tạo một môi trường mới với Python 3.10:

```bash
conda create -n deep_search python=3.10 -y
conda activate deep_search
```

Nếu môi trường `deep_search` đã tồn tại:

```bash
conda activate deep_search
```

Kiểm tra đúng Python của môi trường:

```bash
which python
python --version
```

## 6. Cài thư viện

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra các thư viện quan trọng:

```bash
python -c "import chromadb, sentence_transformers, google.genai; print('OK')"
```

## 7. Tạo Gemini API key và file `.env`

Tạo API key tại [Google AI Studio](https://aistudio.google.com/apikey).

Tạo file `.env` ở thư mục gốc của dự án:

```bash
touch .env
```

Mở `.env` bằng trình soạn thảo và nhập:

```env
GEMINI_API_KEY=thay_bang_api_key_cua_ban
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_MAX_RETRIES=2

RAG_EMBEDDING_MODEL=intfloat/multilingual-e5-base
RAG_EMBEDDING_DEVICE=auto
RAG_TOP_K=5
RAG_MIN_RELEVANCE=0.15
```

Ý nghĩa cấu hình:

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `GEMINI_API_KEY` | Bắt buộc | API key dùng cho Gemini |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model phân tích và viết câu trả lời |
| `GEMINI_MAX_RETRIES` | `2` | Số lần thử lại khi Gemini quá tải |
| `RAG_EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Model embedding local |
| `RAG_EMBEDDING_DEVICE` | `auto` | Tự chọn GPU hoặc CPU; có thể đặt `cuda`/`cpu` |
| `RAG_TOP_K` | `5` | Số chunk tối đa đưa vào câu trả lời |
| `RAG_MIN_RELEVANCE` | `0.15` | Ngưỡng liên quan tối thiểu |
| `ROUTER_MODE` | `auto` | `local` = router chạy hoàn toàn offline; `auto` = local rồi Gemini phân giải khi mơ hồ; `gemini` = luôn gọi Gemini |
| `ROUTER_MARGIN` | `0.03` | Score hạng nhất phải hơn hạng nhì chừng này thì router local mới dám tự quyết |
| `TTS_PROVIDER` | `auto` | `auto` = Gemini trước, hỏng thì FPT; `gemini`/`fpt` = ép một nguồn |
| `FPT_API_KEY` | *(trống)* | Key FPT Cloud Marketplace; bỏ trống = tắt TTS dự phòng |
| `FPT_TTS_MODEL` | `FPT.AI-VITs` | Model TTS dự phòng |
| `FPT_TTS_VOICE` | `std_leminh` | Giọng đọc FPT (nam); giọng nữ: `std_kimngan` |
| `FPT_TTS_FORMAT` | `mp3` | Định dạng FPT trả về; đổi sang `wav` chỉ khi cần gỡ lỗi vì file nặng hơn ~2 lần |
| `TTS_MAX_SECONDS` | `210` | Trần thời lượng audio (3 phút 30); vượt thì cắt chữ rồi cắt cả audio |

Semantic Router chạy local (`heritage_ai/local_router.py`): vector search đã xếp
hạng di sản sẵn và intent tiếng Việt nhận ra được bằng từ khoá, nên câu hỏi rõ
ràng không cần gọi Gemini để phân tích — tiết kiệm ~2.1s mỗi câu. Chỉ khi hai di
sản đầu bảng bám sát nhau (câu mơ hồ kiểu "kể tôi nghe") mới nhờ tới Gemini.

TTS dự phòng: khi Gemini TTS lỗi hoặc hết quota (429), `heritage_ai/voice.py` tự
gọi FPT.AI-VITs để NPC vẫn có tiếng — câu trả lời chữ không bao giờ bị chặn vì
TTS. Mặc định FPT cũng trả `.mp3`; đặt `FPT_TTS_FORMAT=wav` thì thành `.wav` —
proxy `web-ar` hỗ trợ cả hai đuôi.

File `.env` đã được khai báo trong `.gitignore`. Không đưa API key vào code,
ảnh chụp màn hình hoặc GitHub.

## 8. Chuẩn bị dataset

Đặt các PDF chính vào cấu trúc sau:

```text
dataset/
└── di_san_van_hoa_phi_vat_the_485_files_pdf/
    ├── 001_Nhã nhạc - Âm nhạc Cung đình Việt Nam.pdf
    ├── 002_Không gian văn hóa Cồng chiêng Tây Nguyên.pdf
    └── ...
```

Pipeline đọc đệ quy toàn bộ file PDF trong `dataset`. Tên di sản được suy ra từ
tên file; tiền tố số như `001_` được loại bỏ tự động.

Kiểm tra nhanh số lượng PDF:

```bash
find dataset -type f -iname '*.pdf' | wc -l
```

## 9. Tạo VectorDB

### Tạo mới hoàn toàn

Chạy lệnh này lần đầu hoặc sau khi đổi model embedding/chunking:

```bash
python create_vectorDB.py --reset
```

`--reset` xóa collection ChromaDB hiện tại rồi tạo lại. Không dùng tùy chọn này
nếu chỉ muốn bổ sung các file mới mà vẫn giữ index đang có.

Trong quá trình chạy sẽ có thanh tiến trình:

```text
Dataset: 485 trang PDF, 449 tên di sản trong catalog.
Đã đọc 520 phần tài liệu, tạo 522 chunk.
Embedding + ChromaDB: 100%|██████████| 522/522 [...]
Hoàn tất: collection hiện có 522 chunk.
```

### Cập nhật tăng dần

Sau khi thêm tài liệu mới, chạy không có `--reset`:

```bash
python create_vectorDB.py
```

Các chunk có ID không đổi sẽ được bỏ qua.

### Một số tùy chọn

```bash
python create_vectorDB.py --help
python create_vectorDB.py --batch-size 4 --reset
python create_vectorDB.py --no-json --reset
python create_vectorDB.py --no-dataset --reset
python create_vectorDB.py --dataset /duong/dan/dataset --reset
python create_vectorDB.py --storage /duong/dan/chroma --reset
```

Nếu GPU chỉ có ít VRAM, giảm batch:

```bash
python create_vectorDB.py --batch-size 4 --reset
```

Nếu muốn ép chạy CPU, sửa `.env`:

```env
RAG_EMBEDDING_DEVICE=cpu
```

## 10. Chạy chatbot

VectorDB phải được tạo thành công trước khi chạy chatbot.

### Chế độ tương tác

```bash
python run.py
```

Các lệnh trong chế độ tương tác:

- `danhsach`: xem danh sách di sản.
- `thoat`: kết thúc chương trình.

### Hỏi một câu rồi thoát

```bash
python run.py --query "Bài Chòi xuất hiện từ bao giờ?"
```

Có thể viết ngắn bằng `-q`:

```bash
python run.py -q "Hãy giới thiệu về Nhã nhạc cung đình Huế"
```

### Liệt kê các di sản

```bash
python run.py --list
```

## 11. Thêm tài liệu riêng vào RAG

Có thể đặt file `.pdf`, `.txt` hoặc `.md` vào:

```text
heritage_ai/data/documents/
```

Mỗi tài liệu riêng nên có một file metadata cùng tên. Ví dụ:

```text
bai_choi.pdf
bai_choi.pdf.metadata.json
```

Nội dung metadata:

```json
{
  "heritage_id": "nghe-thuat-bai-choi-trung-bo",
  "heritage_name": "Nghệ thuật Bài Chòi Trung Bộ Việt Nam",
  "source": "Tên cơ quan hoặc tài liệu",
  "document_name": "Tên đầy đủ của tài liệu",
  "source_url": "https://dia-chi-nguon-neu-co",
  "section": "Tư liệu chuyên khảo",
  "intent": "history"
}
```

Các giá trị `intent` được hỗ trợ:

- `overview`: tổng quan.
- `history`: nguồn gốc và lịch sử.
- `practice`: cách thực hành/trình diễn.
- `meaning`: ý nghĩa và giá trị.
- `etiquette`: lưu ý ứng xử dành cho du khách.
- `location`: không gian và địa bàn thực hành.
- `all`: dùng cho tất cả loại câu hỏi.

Sau khi thêm hoặc sửa tài liệu:

```bash
python create_vectorDB.py
```

Nếu thay đổi nội dung nhưng hệ thống không nhận ra hoặc đã đổi cách chunking:

```bash
python create_vectorDB.py --reset
```

## 12. Chạy kiểm thử

```bash
python -m unittest discover -s tests -v
```

Kiểm tra cú pháp toàn bộ source:

```bash
python -m compileall -q heritage_ai create_vectorDB.py run.py
```

## 13. Xử lý lỗi thường gặp

### `Chưa có GEMINI_API_KEY`

Kiểm tra `.env` nằm đúng ở thư mục chứa `run.py` và có:

```env
GEMINI_API_KEY=api_key_thuc_te
```

Không đặt dấu cách quanh dấu `=`.

### `503 UNAVAILABLE` hoặc Gemini đang quá tải

Code tự thử lại theo `GEMINI_MAX_RETRIES`. Nếu vẫn lỗi, chờ một lúc rồi chạy
lại. Không cần tạo lại VectorDB.

### Cảnh báo `HF_TOKEN`

Đây chỉ là cảnh báo của Hugging Face, không phải lỗi. Nếu model đã tải xong thì
có thể bỏ qua. Có thể khai báo token Hugging Face trong `.env` nếu cần tải model
thường xuyên:

```env
HF_TOKEN=token_cua_ban
```

### `VectorDB đang dùng model cũ`

Không được trộn vector tạo bởi hai model embedding khác nhau. Tạo lại:

```bash
python create_vectorDB.py --reset
```

### CUDA hết bộ nhớ

Giảm batch:

```bash
python create_vectorDB.py --batch-size 2 --reset
```

Hoặc chuyển sang CPU bằng `RAG_EMBEDDING_DEVICE=cpu`.

### Không tìm thấy tư liệu phù hợp

Kiểm tra:

1. PDF có nằm trong `dataset` không.
2. VectorDB đã được tạo chưa.
3. Tên di sản trong câu hỏi có rõ ràng không.
4. `RAG_MIN_RELEVANCE` có đang đặt quá cao không.

### ChromaDB cũ báo lỗi telemetry hoặc không tương thích

Nâng cấp dependency theo dự án:

```bash
python -m pip install --upgrade -r requirements.txt
```

Sau đó tạo lại VectorDB nếu cần.

## 14. Bảo mật và an toàn

- Không commit `.env`, API key hoặc dữ liệu riêng tư.
- Embedding chạy local, nhưng câu hỏi và các đoạn tư liệu được chọn vẫn được gửi
  tới Gemini để phân tích và tạo câu trả lời.
- Chỉ ingest tài liệu mà bạn có quyền sử dụng.
- Không coi câu trả lời của AI là tư vấn y tế, pháp lý hoặc xử lý khẩn cấp.
- Khi triển khai công khai, cần bổ sung input guard, output guard, rate limit,
  kiểm tra prompt injection và audit log đã ẩn dữ liệu nhạy cảm.
- “Nghệ nhân AI” là nhân vật tổng hợp tư liệu, không giả danh nghệ nhân có thật.

## 15. Quy trình chạy nhanh

Sau khi clone dự án, toàn bộ quy trình tối thiểu là:

```bash
cd Chatbot_DeepSearch
conda create -n deep_search python=3.10 -y
conda activate deep_search
python -m pip install -r requirements.txt

# Tạo .env và điền GEMINI_API_KEY trước khi tiếp tục.

python create_vectorDB.py --reset
python run.py --query "Bài Chòi xuất hiện từ bao giờ?"
```

Những lần chạy sau, nếu dataset không thay đổi:

```bash
conda activate deep_search
cd Chatbot_DeepSearch
python run.py
```
