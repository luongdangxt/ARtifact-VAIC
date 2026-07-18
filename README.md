# Smart Heritage Library

Chatbot tra cuu di san van hoa phi vat the dua tren tai lieu PDF/TXT trong `data/books`.
Du an dung ChromaDB cho retrieval, FPT Cloud Marketplace cho LLM/STT/TTS, va FastAPI cho HTTP API.

## AI va cong nghe duoc su dung

| Thanh phan | Cong nghe/model | Vai tro |
|---|---|---|
| LLM tra loi | `SaoLa3.1-medium` | Hieu cau hoi, tong hop thong tin tu cac doan tai lieu duoc truy xuat |
| Semantic Router | `SaoLa3.1-medium` | Phan loai y dinh truoc retrieval, chan cau hoi ngoai chu de |
| Speech-to-Text | `FPT.AI-whisper-large-v3-turbo` | Chuyen file/ghi am tieng noi thanh van ban |
| Text-to-Speech | `FPT.AI-VITs` | Doc cau tra loi bang tieng Viet va tao file WAV |
| Retrieval database | `ChromaDB` | Luu va tim kiem cac doan noi dung da ingest tu PDF/TXT |
| Embedding local | `HashingEmbedder` | Ma hoa van ban de tim kiem similarity, khong can tai model AI rieng |

Tat ca model FPT Cloud duoc goi qua FPT Cloud Marketplace. Noi dung tra loi duoc gioi han boi cac tai lieu trong `data/books`.

## 1. Cai dat

```powershell
cd "C:\Users\admin\OneDrive\Documents\Chatbot_DeepSearch"
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Mo `.env` va thay:

```env
FPT_API_KEY=your_fpt_marketplace_api_key
```

Khong commit file `.env` len Git.

## 2. Them tai lieu

Dat file `.pdf`, `.txt` hoac `.md` vao `data/books`, sau do chay:

```powershell
python scripts\ingest_pdfs.py
```

Lenh ingest rebuild collection `heritage_chunks` tu noi dung hien co trong `data/books`.
Neu xoa tai lieu cu va ingest tai lieu moi, du lieu cu trong ChromaDB se duoc thay the.

## 3. Chay terminal chatbot

```powershell
python chatbot_terminal.py
```

Lenh trong chatbot: `/audio`, `/reload`, `/help`, `/exit`.

Khong goi TTS:

```powershell
python chatbot_terminal.py --no-tts
```

## 4. Chay HTTP API

```powershell
python scripts\run_api.py
```

API mac dinh tai `http://127.0.0.1:8000`.
Swagger UI tai `http://127.0.0.1:8000/docs`.

Kiem tra server:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Endpoint chinh:

| Method | Path | Chuc nang |
|---|---|---|
| GET | `/health` | Kiem tra server va so ban ghi ChromaDB |
| POST | `/v1/ask` | Hoi bang van ban, tra loi kem nguon |
| POST | `/v1/chat/completions` | API tuong thich OpenAI/FPT Marketplace |
| POST | `/v1/audio/transcriptions` | Audio thanh van ban |
| POST | `/v1/audio/ask` | Audio -> STT -> RAG -> LLM -> TTS |
| POST | `/v1/audio/speech` | Van ban thanh file WAV |

Vi du `/v1/ask` bang PowerShell:

```powershell
$body = @{ question = "Nha nhac cung dinh Hue co nguon goc nhu the nao?"; synthesize = $false } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body $body
```

Vi du TTS:

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/audio/speech `
  -H "Content-Type: application/json" `
  -d '{"input":"Xin chao, toi la Nghe nhan AI","response_format":"wav"}' `
  -o test_tts.wav
```

## 5. Bao mat

Bat Bearer token bang cach dat trong `.env`:

```env
API_AUTH_TOKEN=your_internal_api_token
```

Khi bat, cac endpoint tru `/health` yeu cau header:

```text
Authorization: Bearer your_internal_api_token
```

`.gitignore` bo qua `.env`, ChromaDB, audio, log va cac file tam. Tai lieu trong `data/books` duoc giu lai de dua len repository.

## 6. Kiem tra FPT Cloud

```powershell
python scripts\check_fpt_api.py
python scripts\check_fpt_api.py --llm
python scripts\check_fpt_api.py --stt C:\duong-dan\audio.wav
python scripts\check_fpt_api.py --tts
```

Luu y: request LLM/STT/TTS co the su dung quota FPT Cloud. Du lieu tra loi duoc truy xuat tu kho da ingest trong `data/books`; Semantic Router phan loai y dinh truoc khi truy xuat ChromaDB.
