"""STT + TTS cho backend local.

- TTS chính: Gemini `gemini-2.5-flash-preview-tts` trả PCM 24kHz mono -> encode
  MP3 (lameenc). Câu dài được cắt đoạn ngắn, TTS SONG SONG rồi ghép PCM để giảm
  độ trễ.
- TTS dự phòng: FPT.AI-VITs (mkp-api.fptcloud.com, API kiểu OpenAI), mặc định trả
  MP3 (FPT_TTS_FORMAT). Dùng khi Gemini lỗi/hết quota, hoặc khi ép TTS_PROVIDER=fpt
  — hiện đang ép fpt vì nhanh hơn Gemini TTS hơn 10 lần.
- STT chính: model đa phương thức (gemini-3.1-flash-lite) nhận audio inline ->
  transcript. Gemini nhận thẳng bản ghi nén gốc (webm/mp4/ogg...) nên client
  không cần convert.
- STT dự phòng: FPT.AI-whisper-large-v3-turbo (mkp-api.fptcloud.com, API kiểu
  OpenAI). Endpoint này CHỈ nhận wav/mp3 — webm/opus và mp4/aac đều trả 503 —
  nên bản ghi gốc từ trình duyệt được giải mã sang WAV 16kHz mono trước khi gửi.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import struct
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import requests

_log = logging.getLogger(__name__)

_API = "https://generativelanguage.googleapis.com/v1beta/models"

TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")  # giọng dựng sẵn của Gemini
STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-3.1-flash-lite")

_TTS_SAMPLE_RATE = 24000  # Gemini TTS luôn trả 24kHz mono 16-bit PCM
_TTS_MP3_BITRATE = int(os.getenv("GEMINI_TTS_MP3_BITRATE", "64"))  # kbps, mono
# Trần THỜI LƯỢNG audio trả về: NPC không được nói quá 3 phút 30. Chặn hai lớp —
# (1) cắt bớt chữ theo tốc độ đọc đo được, (2) cắt lại chính audio nếu vẫn quá dài.
_TTS_MAX_SECONDS = float(os.getenv("TTS_MAX_SECONDS", "210"))
# FPT.AI-VITs đọc ~18 ký tự/s (≈255 từ/phút); để 16 cho dư an toàn.
_TTS_CHARS_PER_SECOND = float(os.getenv("TTS_CHARS_PER_SECOND", "16"))
_MAX_TTS_CHARS = min(
    int(os.getenv("TTS_MAX_CHARS", "1500")),  # trần cost cho câu dài bất thường
    int(_TTS_MAX_SECONDS * _TTS_CHARS_PER_SECOND),
)
# Cắt câu trả lời thành đoạn ngắn rồi TTS SONG SONG -> wall-clock ~ đoạn chậm nhất
# thay vì tổng, giảm mạnh độ trễ (TTS cả câu dài mất >30s).
_TTS_MAX_WORDS = int(os.getenv("GEMINI_TTS_MAX_WORDS", "28"))  # ~1-2 câu/đoạn
_TTS_CONCURRENCY = int(os.getenv("GEMINI_TTS_CONCURRENCY", "6"))  # số call TTS song song
# Trần số đoạn: mỗi đoạn = 1 request TTS. Free tier giới hạn REQUEST/NGÀY nên cần chặn
# để câu dài không nổ quota (đặt 0 = bỏ trần). Có billing thì tăng lên cho nhanh hơn.
_TTS_MAX_CHUNKS = int(os.getenv("GEMINI_TTS_MAX_CHUNKS", "10"))

# --- TTS dự phòng: FPT.AI-VITs (endpoint kiểu OpenAI /v1/audio/speech) -------
FPT_TTS_URL = os.getenv("FPT_TTS_URL", "https://mkp-api.fptcloud.com/v1/audio/speech")
FPT_TTS_MODEL = os.getenv("FPT_TTS_MODEL", "FPT.AI-VITs")
FPT_TTS_VOICE = os.getenv("FPT_TTS_VOICE", "std_leminh")  # giọng NAM cho NPC nghệ nhân
# mp3 mặc định: đo trên cùng bộ câu trả lời, mp3 ra 700-880KB còn WAV 1.3-2.1MB
# (nhẹ hơn ~2.3 lần) nên du khách dùng 4G nghe được sớm hơn hẳn. WAV chỉ giữ lại để
# gỡ lỗi hoặc phòng khi FPT đổi hành vi encode.
FPT_TTS_FORMAT = os.getenv("FPT_TTS_FORMAT", "mp3").strip().lower()
# auto = Gemini trước, hỏng thì FPT | gemini = chỉ Gemini | fpt = chỉ FPT.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip().lower()

# --- STT dự phòng: FPT.AI-whisper (endpoint kiểu OpenAI /v1/audio/transcriptions) ---
FPT_STT_URL = os.getenv(
    "FPT_STT_URL", "https://mkp-api.fptcloud.com/v1/audio/transcriptions"
)
FPT_STT_MODEL = os.getenv("FPT_STT_MODEL", "FPT.AI-whisper-large-v3-turbo")
FPT_STT_LANGUAGE = os.getenv("FPT_STT_LANGUAGE", "vi").strip()
# auto = Gemini trước, hỏng thì FPT | gemini = chỉ Gemini | fpt = chỉ FPT.
STT_PROVIDER = os.getenv("STT_PROVIDER", "auto").strip().lower()
# Đã đo trực tiếp: whisper của FPT nhận wav/mp3, còn webm/opus và mp4/aac trả
# 503 "Transcription service unavailable" -> mọi định dạng khác phải giải mã trước.
_FPT_STT_FORMATS = {"wav", "mp3"}
_STT_SAMPLE_RATE = 16000  # whisper resample về 16kHz, gửi sẵn cho nhẹ đường truyền


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
    """Audio -> câu nói tiếng Việt (STT). Gemini là chính, FPT.AI-whisper dự phòng."""
    if STT_PROVIDER == "fpt":
        return transcribe_fpt(audio_bytes, mime_type)

    try:
        return transcribe_gemini(audio_bytes, mime_type)
    except VoiceError as exc:
        if STT_PROVIDER == "gemini" or not _fpt_api_key():
            raise
        # Gemini hỏng (hết quota 429, model lỗi...) -> vẫn nghe được nhờ FPT.
        _log.warning("Gemini STT lỗi, chuyển sang FPT.AI-whisper: %s", exc)
        return transcribe_fpt(audio_bytes, mime_type)


def transcribe_gemini(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Audio -> câu nói tiếng Việt bằng Gemini (nhận thẳng bản ghi nén gốc)."""
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


# MIME của bản ghi -> đuôi file (whisper chọn bộ giải mã theo đuôi trong multipart).
_MIME_EXTS = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mp3": "mp3",
    "audio/mpeg": "mp3",
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "video/mp4": "m4a",
    "audio/aac": "aac",
    "audio/flac": "flac",
    "audio/aiff": "aiff",
}


def _ext_from_mime(mime_type: str) -> str:
    base = (mime_type or "").lower().split(";")[0].strip()
    return _MIME_EXTS.get(base, base.rsplit("/", 1)[-1] or "webm")


def _frame_pcm(frame) -> bytes:
    """PCM thô của một AudioFrame s16 mono.

    Lấy thẳng plane thay vì to_ndarray() để không kéo theo numpy; buffer của plane
    được ffmpeg căn lề nên phải cắt đúng samples * 2 byte, phần đệm dư là rác.
    """
    return bytes(frame.planes[0])[: frame.samples * 2]


def _decode_to_wav(audio_bytes: bytes) -> bytes:
    """Bản ghi nén (webm/opus, mp4/aac, ogg...) -> WAV 16kHz mono 16-bit.

    Dùng PyAV (bundle sẵn thư viện ffmpeg trong wheel) nên image không cần cài
    ffmpeg riêng. Chỉ chạy ở đường dự phòng, tức khi Gemini STT đã hỏng.
    """
    try:
        import av
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise VoiceError(
            "Chưa cài av (PyAV) để chuyển bản ghi sang WAV cho FPT STT."
        ) from exc

    try:
        with av.open(io.BytesIO(audio_bytes)) as container:
            stream = next(
                (s for s in container.streams if s.type == "audio"), None
            )
            if stream is None:
                raise VoiceError("Bản ghi không có luồng âm thanh.")
            resampler = av.AudioResampler(
                format="s16", layout="mono", rate=_STT_SAMPLE_RATE
            )
            pcm = bytearray()
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    pcm += _frame_pcm(out)
            for out in resampler.resample(None):  # xả nốt bộ đệm resample
                pcm += _frame_pcm(out)
    except VoiceError:
        raise
    except Exception as exc:  # av.AVError và họ hàng
        raise VoiceError(f"Không giải mã được bản ghi để gửi FPT STT: {exc}") from exc

    if not pcm:
        raise VoiceError("Bản ghi không có dữ liệu âm thanh.")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_STT_SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return buffer.getvalue()


def transcribe_fpt(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Audio -> câu nói tiếng Việt bằng FPT.AI-whisper (1 request multipart)."""
    key = _fpt_api_key()
    if not key:
        raise VoiceError("Chưa có FPT_API_KEY cho STT dự phòng.")

    ext = _ext_from_mime(mime_type)
    if ext not in _FPT_STT_FORMATS:
        audio_bytes = _decode_to_wav(audio_bytes)
        ext = "wav"

    data = {"model": FPT_STT_MODEL}
    if FPT_STT_LANGUAGE:
        data["language"] = FPT_STT_LANGUAGE
    try:
        resp = requests.post(
            FPT_STT_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=data,
            files={"file": (f"question.{ext}", audio_bytes, f"audio/{ext}")},
            timeout=90,
        )
    except requests.RequestException as exc:
        raise VoiceError(f"FPT STT không kết nối được: {exc}") from exc

    if resp.status_code != 200:
        raise VoiceError(f"FPT STT lỗi HTTP {resp.status_code}: {resp.text[:160]}")

    try:
        text = (resp.json().get("text") or "").strip()
    except ValueError as exc:
        raise VoiceError(f"FPT STT trả về dữ liệu lạ: {resp.text[:160]}") from exc
    if not text:
        raise VoiceError("Không nhận diện được lời nói.")
    return text


def synthesize(text: str) -> tuple[bytes, str]:
    """Chữ -> (audio bytes, đuôi file). Gemini là chính, FPT.AI-VITs là dự phòng.

    Trả kèm đuôi vì hai nguồn cho định dạng khác nhau (mp3 vs wav); phía API dùng
    đuôi này để đặt tên file + Content-Type.
    """
    if TTS_PROVIDER == "fpt":
        return synthesize_fpt(text)

    try:
        return synthesize_mp3(text), "mp3"
    except VoiceError as exc:
        if TTS_PROVIDER == "gemini" or not _fpt_api_key():
            raise
        # Gemini hỏng (hết quota 429, model lỗi...) -> vẫn có tiếng nhờ FPT.
        _log.warning("Gemini TTS lỗi, chuyển sang FPT.AI-VITs: %s", exc)
        return synthesize_fpt(text)


def _fpt_api_key() -> str:
    return (os.getenv("FPT_API_KEY") or "").strip()


def _fit_text(text: str) -> str:
    """Cắt bớt chữ cho vừa trần thời lượng, ưu tiên dừng ở hết câu."""
    spoken = text.strip()
    if len(spoken) <= _MAX_TTS_CHARS:
        return spoken
    cut = spoken[:_MAX_TTS_CHARS]
    stop = max(cut.rfind(mark) for mark in ".!?…")
    if stop > _MAX_TTS_CHARS // 2:  # có dấu kết câu đủ gần cuối thì dừng ở đó
        cut = cut[: stop + 1]
    _log.warning(
        "Nội dung đọc dài %d ký tự, cắt còn %d để audio dưới %.0fs",
        len(spoken),
        len(cut),
        _TTS_MAX_SECONDS,
    )
    return cut.strip()


def _trim_wav(wav: bytes) -> bytes:
    """Cắt WAV về đúng trần thời lượng (chỉ dùng tới khi TTS trả quá dài)."""
    if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        return wav
    byte_rate = 0
    offset = 12
    while offset + 8 <= len(wav):
        chunk_id = wav[offset : offset + 4]
        declared = struct.unpack_from("<I", wav, offset + 4)[0]
        body = offset + 8
        if chunk_id == b"fmt ":
            byte_rate = struct.unpack_from("<I", wav, body + 8)[0]
        elif chunk_id == b"data":
            # FPT khai size sai (gấp đôi) nên tính theo độ dài thật của file.
            actual = len(wav) - body
            if not byte_rate:
                return wav
            keep = int(byte_rate * _TTS_MAX_SECONDS)
            keep -= keep % 4  # dừng đúng biên mẫu, không cắt giữa sample
            if actual <= keep:
                return wav
            _log.warning(
                "Audio FPT dài %.0fs, cắt còn %.0fs",
                actual / byte_rate,
                keep / byte_rate,
            )
            trimmed = bytearray(wav[: body + keep])
            struct.pack_into("<I", trimmed, 4, len(trimmed) - 8)
            struct.pack_into("<I", trimmed, offset + 4, keep)
            return bytes(trimmed)
        offset = body + declared + (declared % 2)
    return wav


def _looks_like_audio(data: bytes, fmt: str) -> bool:
    """Nhận diện audio thật qua magic bytes (lỗi ứng dụng của FPT vẫn trả HTTP 200)."""
    if fmt == "wav":
        return data.startswith(b"RIFF")
    # MP3: hoặc có tag ID3, hoặc bắt đầu thẳng bằng frame sync 11 bit (0xFF 0xEx/0xFx).
    return data.startswith(b"ID3") or (
        len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    )


def synthesize_fpt(text: str) -> tuple[bytes, str]:
    """Chữ -> (audio bytes, đuôi file) bằng FPT.AI-VITs (1 request cho cả câu trả lời)."""
    spoken = _fit_text(text)
    if not spoken:
        raise VoiceError("Không có nội dung để đọc.")
    key = _fpt_api_key()
    if not key:
        raise VoiceError("Chưa có FPT_API_KEY cho TTS dự phòng.")

    fmt = FPT_TTS_FORMAT if FPT_TTS_FORMAT in {"mp3", "wav"} else "mp3"
    payload = {
        "model": FPT_TTS_MODEL,
        "input": spoken,
        "response_format": fmt,
        "voice": FPT_TTS_VOICE,
    }
    try:
        resp = requests.post(
            FPT_TTS_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=90,
        )
    except requests.RequestException as exc:
        raise VoiceError(f"FPT TTS không kết nối được: {exc}") from exc

    if resp.status_code != 200:
        raise VoiceError(f"FPT TTS lỗi HTTP {resp.status_code}: {resp.text[:160]}")

    audio = resp.content
    # Lỗi ứng dụng (hết quota, input bị từ chối...) vẫn trả 200 kèm JSON, không phải audio.
    if not _looks_like_audio(audio, fmt):
        raise VoiceError(f"FPT TTS không trả về {fmt}: {audio[:160]!r}")
    # MP3 không cắt được bằng cách xén byte như WAV; trần thời lượng đã được _fit_text
    # bảo đảm từ phía chữ nên đây chỉ là lớp chặn thứ hai cho WAV.
    return (_trim_wav(audio) if fmt == "wav" else audio), fmt


def synthesize_mp3(text: str) -> bytes:
    """Chữ -> MP3 (TTS). Cắt đoạn ngắn, TTS song song, ghép PCM rồi encode 1 file MP3."""
    spoken = _fit_text(text)
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

    pcm = b"".join(pcm_parts)
    max_bytes = int(_TTS_SAMPLE_RATE * 2 * _TTS_MAX_SECONDS)  # 16-bit mono
    if len(pcm) > max_bytes:
        _log.warning(
            "Audio Gemini dài %.0fs, cắt còn %.0fs",
            len(pcm) / (_TTS_SAMPLE_RATE * 2),
            _TTS_MAX_SECONDS,
        )
        pcm = pcm[: max_bytes - max_bytes % 2]
    return _pcm_to_mp3(pcm, _TTS_SAMPLE_RATE)


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
