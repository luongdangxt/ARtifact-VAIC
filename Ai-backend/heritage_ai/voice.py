"""STT + TTS bằng Gemini API (REST) cho backend local.

Dùng CHUNG GEMINI_API_KEY với phần text — không cần dịch vụ ngoài (FPT...).
- TTS: `gemini-2.5-flash-preview-tts` trả PCM 24kHz mono -> encode MP3 (lameenc).
  Câu dài được cắt đoạn ngắn, TTS SONG SONG rồi ghép PCM để giảm độ trễ.
- STT: model đa phương thức (gemini-3.1-flash-lite) nhận audio inline -> transcript.
  Gemini nhận thẳng bản ghi nén gốc (webm/mp4/ogg...) nên client không cần convert.
"""

from __future__ import annotations

import base64
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

_API = "https://generativelanguage.googleapis.com/v1beta/models"

TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")  # giọng dựng sẵn của Gemini
STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-3.1-flash-lite")

_TTS_SAMPLE_RATE = 24000  # Gemini TTS luôn trả 24kHz mono 16-bit PCM
_TTS_MP3_BITRATE = int(os.getenv("GEMINI_TTS_MP3_BITRATE", "64"))  # kbps, mono
_MAX_TTS_CHARS = 1500  # trần nội dung đọc (tránh cost quá lớn cho câu dài bất thường)
# Cắt câu trả lời thành đoạn ngắn rồi TTS SONG SONG -> wall-clock ~ đoạn chậm nhất
# thay vì tổng, giảm mạnh độ trễ (TTS cả câu dài mất >30s).
_TTS_MAX_WORDS = int(os.getenv("GEMINI_TTS_MAX_WORDS", "28"))  # ~1-2 câu/đoạn
_TTS_CONCURRENCY = int(os.getenv("GEMINI_TTS_CONCURRENCY", "6"))  # số call TTS song song
# Trần số đoạn: mỗi đoạn = 1 request TTS. Free tier giới hạn REQUEST/NGÀY nên cần chặn
# để câu dài không nổ quota (đặt 0 = bỏ trần). Có billing thì tăng lên cho nhanh hơn.
_TTS_MAX_CHUNKS = int(os.getenv("GEMINI_TTS_MAX_CHUNKS", "10"))


class VoiceError(RuntimeError):
    """Lỗi khi gọi STT/TTS."""


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise VoiceError("Chưa có GEMINI_API_KEY.")
    return key


def _post(model: str, payload: dict) -> dict:
    # Retry nhẹ khi tạm lỗi (429/5xx) — gọi TTS song song dễ chạm rate limit.
    last: str = ""
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{_API}/{model}:generateContent",
                headers={
                    "x-goog-api-key": _api_key(),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
        except requests.RequestException as exc:
            last = str(exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}: {resp.text[:160]}"
            if resp.status_code not in {429, 500, 502, 503, 504}:
                break
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    raise VoiceError(f"Gemini {model} lỗi: {last}")


def _first_part(data: dict) -> dict:
    try:
        return data["candidates"][0]["content"]["parts"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceError("Gemini không trả về nội dung dùng được.") from exc


def transcribe(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Audio -> câu nói tiếng Việt (STT)."""
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Chép lại chính xác lời nói tiếng Việt trong đoạn âm "
                            "thanh. Chỉ trả về đúng câu nói, không thêm gì khác."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(audio_bytes).decode(),
                        }
                    },
                ]
            }
        ]
    }
    text = (_first_part(_post(STT_MODEL, payload)).get("text") or "").strip()
    if not text:
        raise VoiceError("Không nhận diện được lời nói.")
    return text


def synthesize_mp3(text: str) -> bytes:
    """Chữ -> MP3 (TTS). Cắt đoạn ngắn, TTS song song, ghép PCM rồi encode 1 file MP3."""
    spoken = text.strip()[:_MAX_TTS_CHARS]
    chunks = _split_for_tts(spoken, _TTS_MAX_WORDS)
    if not chunks:
        raise VoiceError("Không có nội dung để đọc.")

    if len(chunks) == 1:
        pcm_parts = [_tts_pcm(chunks[0])]
    else:
        # Giữ THỨ TỰ đoạn (pool.map trả theo thứ tự input) để ghép audio liền mạch.
        workers = min(_TTS_CONCURRENCY, len(chunks))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pcm_parts = list(pool.map(_tts_pcm, chunks))

    return _pcm_to_mp3(b"".join(pcm_parts), _TTS_SAMPLE_RATE)


def _tts_pcm(text: str) -> bytes:
    """TTS 1 đoạn -> PCM thô (24kHz mono 16-bit)."""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}
            },
        },
    }
    b64 = (_first_part(_post(TTS_MODEL, payload)).get("inlineData") or {}).get("data")
    if not b64:
        raise VoiceError("Gemini TTS không trả về audio.")
    return base64.b64decode(b64)


# Tách câu (giữ dấu câu) rồi gộp thành đoạn <= max_words để TTS nhanh, ngắt tự nhiên.
_SENTENCE_RE = re.compile(r"[^.!?…;:\n]+[.!?…;:]*", re.UNICODE)


def _split_for_tts(text: str, max_words: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    sentences = [m.group().strip() for m in _SENTENCE_RE.finditer(text)]
    sentences = [s for s in sentences if s] or [text]

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if current:
            chunks.append(" ".join(current))
            current = []
            current_words = 0

    for sentence in sentences:
        words = sentence.split()
        if len(words) > max_words:
            # Câu quá dài -> cắt cứng theo số từ để không có đoạn nào quá lớn.
            flush()
            for i in range(0, len(words), max_words):
                chunks.append(" ".join(words[i : i + max_words]))
            continue
        if current_words + len(words) > max_words:
            flush()
        current.append(sentence)
        current_words += len(words)
    flush()

    # Chặn cứng số đoạn (= số request TTS) để câu dài không nổ quota free tier:
    # gộp các đoạn liền kề đều nhau về <= _TTS_MAX_CHUNKS.
    if _TTS_MAX_CHUNKS > 0 and len(chunks) > _TTS_MAX_CHUNKS:
        group = -(-len(chunks) // _TTS_MAX_CHUNKS)  # ceil(len/max)
        chunks = [
            " ".join(chunks[i : i + group]) for i in range(0, len(chunks), group)
        ]
    return chunks


def _pcm_to_mp3(pcm: bytes, sample_rate: int) -> bytes:
    """PCM 16-bit mono -> MP3 bằng lameenc (thuần Python, không cần ffmpeg)."""
    try:
        import lameenc
    except ImportError as exc:  # pragma: no cover
        raise VoiceError("Chưa cài lameenc để encode MP3.") from exc
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(_TTS_MP3_BITRATE)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)  # 2 = chất lượng cao, vẫn đủ nhanh
    return bytes(encoder.encode(pcm)) + bytes(encoder.flush())


# Cắt phần đuôi không nên đọc thành tiếng (nguồn, gợi ý hỏi tiếp, lưu ý) + mã [1].
_TRAILER_RE = re.compile(
    r"\n+\s*(nguồn tham khảo|bạn có thể hỏi tiếp|lưu ý)\b.*",
    re.IGNORECASE | re.DOTALL,
)
_CITATION_RE = re.compile(r"\s*\[\d+\]")


def spoken_text(answer: str) -> str:
    """Bản rút gọn của câu trả lời để đọc TTS (bỏ trích dẫn + phần nguồn/gợi ý)."""
    text = _TRAILER_RE.sub("", answer)
    text = _CITATION_RE.sub("", text)
    cleaned = " ".join(text.split()).strip()
    return cleaned or answer.strip()
