"""HTTP API (FastAPI) bọc HeritageChatbot cho web-ar gọi qua proxy /api/ai*.

- /v1/ask          : hỏi bằng CHỮ (+ TTS nếu synthesize=true)
- /v1/audio/ask    : hỏi bằng GIỌNG (STT -> trả lời -> TTS)
- /v1/audio/files/ : serve WAV do TTS sinh (lưu tạm trong RAM)

STT/TTS chạy bằng Gemini (heritage_ai/voice.py), dùng chung GEMINI_API_KEY.

Chạy:  uvicorn heritage_ai.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from heritage_ai import voice as voice_mod
from heritage_ai.orchestrator import HeritageChatbot

_log = logging.getLogger("heritage_ai.api")

# Khởi tạo lười: model embedding + ChromaDB mở lúc dùng lần đầu. Nạp mất ~15s nên
# _warmup() chạy sẵn lúc startup để người hỏi đầu tiên không phải chờ.
_chatbot: HeritageChatbot | None = None
_chatbot_lock = threading.Lock()


def _warmup() -> None:
    """Nạp sẵn chatbot + model embedding (chạy nền, không chặn server nhận request)."""
    started = time.perf_counter()
    try:
        # Một truy vấn vector rỗng nghĩa là đủ để sentence-transformers nạp weight;
        # chỉ chạy local, không tốn quota Gemini.
        _get_chatbot().retriever.candidate_heritage_names("khởi động")
    except Exception as exc:  # noqa: BLE001 - hỏng warmup không được làm chết server
        _log.warning("Nạp sẵn thất bại, request đầu sẽ chậm: %s", exc)
    else:
        _log.info("Đã nạp sẵn chatbot trong %.1fs", time.perf_counter() - started)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=_warmup, name="heritage-warmup", daemon=True).start()
    yield


app = FastAPI(title="Heritage AI API", version="0.2.0", lifespan=lifespan)

# Kho WAV tạm (TTS) trong RAM: proxy web-ar lấy ngay sau khi hỏi nên không cần đĩa.
_AUDIO_STORE: "OrderedDict[str, bytes]" = OrderedDict()
_AUDIO_STORE_CAP = 64


def _get_chatbot() -> HeritageChatbot:
    global _chatbot
    # Khoá để request đến trong lúc warmup chưa xong không nạp model lần thứ hai.
    with _chatbot_lock:
        if _chatbot is None:
            _chatbot = HeritageChatbot()
        return _chatbot


def _build_query(question: str, persona_craft: str | None) -> str:
    """Neo đúng di sản khi câu hỏi ngắn/mơ hồ bằng cách chèn craft của nghệ nhân."""
    craft = (persona_craft or "").strip()
    if craft and craft.casefold() not in question.casefold():
        return f"{question}\n(Bối cảnh di sản: {craft})"
    return question


def _store_audio(data: bytes, ext: str) -> str:
    name = f"{uuid.uuid4().hex}.{ext}"
    _AUDIO_STORE[name] = data
    while len(_AUDIO_STORE) > _AUDIO_STORE_CAP:
        _AUDIO_STORE.popitem(last=False)
    return name


def _synthesize_url(answer: str) -> str | None:
    """TTS câu trả lời -> URL file audio (proxy sẽ stream). None nếu TTS lỗi.

    voice.synthesize tự chọn nguồn: Gemini (mp3) và dự phòng FPT.AI-VITs (wav).
    """
    try:
        audio, ext = voice_mod.synthesize(voice_mod.spoken_text(answer))
    except voice_mod.VoiceError as exc:
        # Cả hai nguồn TTS đều hỏng -> vẫn giữ câu trả lời chữ, chỉ log để biết.
        _log.warning("TTS thất bại: %s", exc)
        return None
    return f"/v1/audio/files/{_store_audio(audio, ext)}"


# MIME phát nhạc theo đuôi file (dùng khi serve /v1/audio/files).
_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
}

# Đuôi -> MIME mà Gemini STT chấp nhận (đã kiểm chứng nhận cả webm/mp4).
_STT_MIMES = {
    "wav": "audio/wav",
    "mp3": "audio/mp3",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "aiff": "audio/aiff",
}


def _stt_mime(file: UploadFile) -> str:
    """MIME cho Gemini STT, ưu tiên đuôi file (client gửi đúng đuôi theo bản ghi)."""
    name = (file.filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in _STT_MIMES:
        return _STT_MIMES[ext]
    content_type = (file.content_type or "").lower().split(";")[0]
    if content_type.startswith("audio/") or content_type.startswith("video/"):
        return content_type
    return "audio/webm"  # mặc định = bản ghi gốc phổ biến của MediaRecorder


def _wants_tts(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _asked_from_json(history_json: str) -> list[str]:
    """Rút các câu du khách đã hỏi từ history dạng JSON của form multipart.

    History hỏng không được làm chết request — cùng lắm mất phần lọc gợi ý trùng.
    """
    try:
        turns = json.loads(history_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(turns, list):
        return []
    return [
        turn["content"]
        for turn in turns
        if isinstance(turn, dict)
        and turn.get("role") == "user"
        and isinstance(turn.get("content"), str)
    ]


class HistoryTurn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    synthesize: bool = False
    history: list[HistoryTurn] = []
    persona_name: str | None = None
    persona_craft: str | None = None
    persona_bio: str | None = None


class AskResponse(BaseModel):
    answer: str
    audio_url: str | None = None


class AudioAskResponse(BaseModel):
    answer: str
    transcript: str | None = None
    audio_url: str | None = None


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "heritage-ai"}


@app.post("/v1/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")

    asked = [turn.content for turn in req.history if turn.role == "user"]
    answer = _get_chatbot().ask(_build_query(question, req.persona_craft), asked=asked)
    audio_url = _synthesize_url(answer) if req.synthesize else None
    return AskResponse(answer=answer, audio_url=audio_url)


@app.post("/v1/audio/ask", response_model=AudioAskResponse)
async def audio_ask(
    file: UploadFile = File(...),
    synthesize: str = Form("true"),
    history_json: str = Form("[]"),
    persona_name: str | None = Form(None),
    persona_craft: str | None = Form(None),
    persona_bio: str | None = Form(None),
) -> AudioAskResponse:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Thiếu dữ liệu âm thanh.")

    try:
        transcript = voice_mod.transcribe(audio_bytes, _stt_mime(file))
    except voice_mod.VoiceError as exc:
        raise HTTPException(status_code=502, detail=f"STT lỗi: {exc}") from exc

    answer = _get_chatbot().ask(
        _build_query(transcript, persona_craft), asked=_asked_from_json(history_json)
    )
    audio_url = _synthesize_url(answer) if _wants_tts(synthesize) else None
    return AudioAskResponse(answer=answer, transcript=transcript, audio_url=audio_url)


@app.get("/v1/audio/files/{name}")
def audio_file(name: str) -> Response:
    data = _AUDIO_STORE.get(name)
    if data is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy audio (đã hết hạn).")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "mp3"
    return Response(content=data, media_type=_CONTENT_TYPES.get(ext, "audio/mpeg"))
