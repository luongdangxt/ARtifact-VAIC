from __future__ import annotations

import json
from pathlib import Path
import time
import uuid
import urllib.error
import urllib.request

from .config import Settings
from .models import SpeechAudio, SpeechTranscript


def format_http_error(provider: str, exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace").strip()
    if exc.code == 401:
        return (
            f"{provider} trả về 401 Unauthorized. "
            "FPT Cloud đã nhận request nhưng từ chối Bearer token. Hãy kiểm tra FPT_API_KEY lấy từ Marketplace API Key."
            + (f" Chi tiết: {detail}" if detail else "")
        )
    if exc.code == 403:
        return (
            f"{provider} trả về 403 Forbidden. "
            "Key có thể đúng nhưng chưa được quyền dùng model này hoặc đã hết quota."
            + (f" Chi tiết: {detail}" if detail else "")
        )
    if detail:
        return f"{provider} HTTP {exc.code}: {detail}"
    return f"{provider} HTTP {exc.code}: {exc.reason}"


def format_url_error(provider: str, exc: urllib.error.URLError) -> str:
    return f"{provider} không kết nối được: {exc.reason}"


class FPTSpeechToText:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "application/octet-stream",
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> SpeechTranscript:
        if not self.settings.fpt_api_key:
            raise RuntimeError("Chưa cấu hình FPT_API_KEY trong file .env nên không thể nhận dạng âm thanh.")

        body, multipart_type = _build_multipart_form(
            fields={
                "model": self.settings.fpt_stt_model,
                "response_format": "json",
                "language": language or self.settings.fpt_stt_language,
            },
            files={
                "file": (filename, content_type, audio_bytes),
            },
        )
        request = urllib.request.Request(
            self.settings.fpt_asr_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.fpt_api_key}",
                "Content-Type": multipart_type,
                "User-Agent": "ChatbotDeepSearch/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_body = response.read()
                response_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(format_http_error("FPT Cloud STT", exc)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(format_url_error("FPT Cloud STT", exc)) from exc

        text, raw = _extract_transcript(response_body, response_type)
        return SpeechTranscript(
            text=text,
            provider="fpt_cloud",
            request_id=_extract_request_id(raw),
            raw=raw if isinstance(raw, dict) else {"text": text},
        )


class FPTTextToSpeech:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, text: str) -> SpeechAudio:
        if not self.settings.fpt_api_key:
            return SpeechAudio(
                audio_url=None,
                provider="mock",
                raw={"reason": "Chưa cấu hình FPT_API_KEY."},
            )

        payload = {
            "model": self.settings.fpt_tts_model,
            "input": text,
            "response_format": "wav",
            "voice": self.settings.fpt_tts_voice,
        }
        request = urllib.request.Request(
            self.settings.fpt_tts_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.fpt_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChatbotDeepSearch/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                audio_bytes = response.read()
                response_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(format_http_error("FPT Cloud TTS", exc)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(format_url_error("FPT Cloud TTS", exc)) from exc

        _raise_if_json_error(audio_bytes, response_type)
        # FPT.AI-VITs đôi khi trả PCM WAV có RIFF/data chunk size lớn gấp đôi
        # số byte thực tế. Một số desktop player vẫn phát được, nhưng Safari và
        # Web Audio API có thể từ chối decode với EncodingError. Chuẩn hoá header
        # trước khi lưu để mọi client nhận cùng một file WAV hợp lệ.
        audio_bytes = normalize_wav_header(audio_bytes)
        output_path = self._write_audio(audio_bytes)
        return SpeechAudio(
            audio_url=str(output_path),
            provider="fpt_cloud",
            request_id=None,
            raw={"model": self.settings.fpt_tts_model, "voice": self.settings.fpt_tts_voice},
        )

    def _write_audio(self, audio_bytes: bytes) -> Path:
        output_dir = self.settings.root_dir / "logs" / "tts"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"fpt_vits_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        output_path.write_bytes(audio_bytes)
        return output_path


def _build_multipart_form(
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----ChatbotDeepSearch{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for name, (filename, content_type, data) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                data,
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _extract_transcript(response_body: bytes, response_type: str) -> tuple[str, dict | str]:
    decoded = response_body.decode("utf-8", errors="replace").strip()
    if "json" not in response_type.lower() and not decoded.startswith(("{", "[")):
        return decoded, decoded

    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return decoded, decoded

    text = _find_text(payload)
    if not text:
        raise RuntimeError(f"FPT Cloud STT không trả về transcript: {payload}")
    return text, payload


def _find_text(payload) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("text", "transcript", "utterance"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if data is not None:
            found = _find_text(data)
            if found:
                return found
        hypotheses = payload.get("hypotheses")
        if isinstance(hypotheses, list):
            for item in hypotheses:
                found = _find_text(item)
                if found:
                    return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_text(item)
            if found:
                return found
    return ""


def _extract_request_id(raw) -> str | None:
    if isinstance(raw, dict):
        value = raw.get("id") or raw.get("request_id")
        if isinstance(value, str):
            return value
    return None


def _raise_if_json_error(audio_bytes: bytes, response_type: str) -> None:
    head = audio_bytes[:1]
    if "json" not in response_type.lower() and head not in {b"{", b"["}:
        return

    decoded = audio_bytes.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return
    raise RuntimeError(f"FPT Cloud TTS trả về JSON thay vì audio: {payload}")


def normalize_wav_header(audio_bytes: bytes) -> bytes:
    """Validate a RIFF/WAVE response and repair incorrect RIFF/data sizes.

    FPT's PCM payload is otherwise valid, but its size fields have been observed
    to describe twice the bytes actually returned. Browsers are stricter about
    this than ffmpeg/desktop players, so use the real response length as truth.
    """
    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise RuntimeError("FPT Cloud TTS không trả về file RIFF/WAVE hợp lệ.")

    normalized = bytearray(audio_bytes)
    normalized[4:8] = (len(normalized) - 8).to_bytes(4, "little")

    offset = 12
    while offset + 8 <= len(normalized):
        chunk_id = bytes(normalized[offset : offset + 4])
        declared_size = int.from_bytes(normalized[offset + 4 : offset + 8], "little")
        data_offset = offset + 8

        if chunk_id == b"data":
            actual_size = len(normalized) - data_offset
            if actual_size <= 0:
                raise RuntimeError("FPT Cloud TTS trả về WAV không có dữ liệu âm thanh.")
            normalized[offset + 4 : offset + 8] = actual_size.to_bytes(4, "little")
            return bytes(normalized)

        next_offset = data_offset + declared_size + (declared_size % 2)
        if next_offset > len(normalized):
            raise RuntimeError("FPT Cloud TTS trả về WAV có chunk bị cắt ngắn.")
        offset = next_offset

    raise RuntimeError("FPT Cloud TTS trả về WAV không có data chunk.")
