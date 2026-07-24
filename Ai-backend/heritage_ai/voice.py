"""STT + TTS bằng Gemini API (REST) cho backend local.

Dùng CHUNG GEMINI_API_KEY với phần text — không cần dịch vụ ngoài (FPT...).
- TTS: model `gemini-2.5-flash-preview-tts` trả PCM 24kHz mono 16-bit -> bọc WAV.
- STT: model đa phương thức (gemini-3.1-flash-lite) nhận audio inline -> transcript.
web-ar tự convert câu hỏi sang WAV trên browser nên STT nhận audio/wav là chính.
"""

from __future__ import annotations

import base64
import os
import re

import requests

_API = "https://generativelanguage.googleapis.com/v1beta/models"

TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")  # giọng dựng sẵn của Gemini
STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-3.1-flash-lite")

_TTS_SAMPLE_RATE = 24000  # Gemini TTS luôn trả 24kHz mono 16-bit PCM
_TTS_MP3_BITRATE = int(os.getenv("GEMINI_TTS_MP3_BITRATE", "64"))  # kbps, mono
_MAX_TTS_CHARS = 1200  # cắt bớt để TTS nhanh + tránh giới hạn token


class VoiceError(RuntimeError):
    """Lỗi khi gọi STT/TTS."""


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise VoiceError("Chưa có GEMINI_API_KEY.")
    return key


def _post(model: str, payload: dict) -> dict:
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
        raise VoiceError(f"Không gọi được Gemini ({model}): {exc}") from exc
    if resp.status_code != 200:
        raise VoiceError(f"Gemini {model} lỗi {resp.status_code}: {resp.text[:200]}")
    return resp.json()


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
    """Chữ -> MP3 (TTS). Gemini trả PCM 24kHz mono -> encode MP3 cho nhẹ (~10× WAV)."""
    spoken = text.strip()[:_MAX_TTS_CHARS]
    if not spoken:
        raise VoiceError("Không có nội dung để đọc.")
    payload = {
        "contents": [{"parts": [{"text": spoken}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}
            },
        },
    }
    inline = _first_part(_post(TTS_MODEL, payload)).get("inlineData") or {}
    b64 = inline.get("data")
    if not b64:
        raise VoiceError("Gemini TTS không trả về audio.")
    return _pcm_to_mp3(base64.b64decode(b64), _TTS_SAMPLE_RATE)


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
