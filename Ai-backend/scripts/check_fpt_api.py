from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import mimetypes
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.console import configure_utf8_console
from app.fpt_speech import FPTSpeechToText, FPTTextToSpeech
from app.llm import extract_chat_response_content


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Kiểm tra kết nối trực tiếp tới FPT Cloud Marketplace API.")
    parser.add_argument("--tts", action="store_true", help="Gọi thử FPT.AI-VITs Text-to-Speech.")
    parser.add_argument("--stt", default=None, help="Gọi thử FPT.AI Whisper bằng file âm thanh.")
    parser.add_argument("--llm", action="store_true", help="Gọi thử SaoLa3.1-medium Chat Completions.")
    parser.add_argument("--text", default="Kiểm tra kết nối FPT.", help="Nội dung dùng để test TTS/LLM.")
    parser.add_argument("--stream", dest="stream", action="store_true", default=None, help="Goi LLM voi stream=true.")
    parser.add_argument("--no-stream", dest="stream", action="store_false", help="Goi LLM voi stream=false.")
    parser.add_argument("--language", default=None, help="Ngon ngu STT, vi du: vi hoac en.")
    args = parser.parse_args()

    settings = Settings.from_env()
    _print_config(settings)

    if not args.tts and not args.stt and not args.llm:
        print("\nChưa gọi API thật. Thêm --tts, --stt <file> hoặc --llm để kiểm tra request ra FPT.")
        return

    if args.tts:
        _test_tts(settings, args.text)

    if args.stt:
        _test_stt(settings, args.stt, args.language)

    if args.llm:
        stream = settings.llm_stream if args.stream is None else args.stream
        _test_llm(settings, args.text, stream)


def _print_config(settings: Settings) -> None:
    dot_env_count = _count_dotenv_keys("FPT_API_KEY")
    print("Cấu hình FPT Cloud Marketplace hiện tại:")
    print(f"- FPT_ASR_URL={settings.fpt_asr_url}")
    print(f"- FPT_STT_MODEL={settings.fpt_stt_model}")
    print(f"- FPT_STT_LANGUAGE={settings.fpt_stt_language}")
    print(f"- FPT_TTS_URL={settings.fpt_tts_url}")
    print(f"- FPT_TTS_MODEL={settings.fpt_tts_model}")
    print(f"- FPT_TTS_VOICE={settings.fpt_tts_voice}")
    print(f"- FPT_TTS_FORMAT={settings.fpt_tts_format}")
    print(f"- VECTOR_STORE_PATH={settings.vector_store_path}")
    print(f"- VECTOR_COLLECTION_NAME={settings.vector_collection_name}")
    print(f"- LLM_PROVIDER={settings.llm_provider}")
    print(f"- LLM_API_BASE={settings.llm_api_base}")
    print(f"- LLM_MODEL={settings.llm_model}")
    print(f"- LLM_STREAM={settings.llm_stream}")
    print(f"- FPT_API_KEY: {_describe_key(settings.fpt_api_key)}")
    print(f"- Số dòng FPT_API_KEY trong .env: {dot_env_count}")
    print("\nChatbot hiện dùng Bearer token của FPT Cloud Marketplace cho STT/TTS/LLM.")


def _describe_key(value: str) -> str:
    if not value:
        return "chưa cấu hình"
    if value.startswith("AIza"):
        return f"trông giống khóa Google AI, độ dài {len(value)} ký tự, vân tay {_fingerprint(value)}"
    return f"đã cấu hình, độ dài {len(value)} ký tự, vân tay {_fingerprint(value)}"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _count_dotenv_keys(name: str) -> int:
    path = ROOT / ".env"
    if not path.exists():
        return 0
    count = 0
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _ = line.split("=", 1)
        if key.strip() == name:
            count += 1
    return count


def _test_tts(settings: Settings, text: str) -> None:
    print("\nĐang gọi thử FPT.AI-VITs Text-to-Speech...")
    try:
        audio = FPTTextToSpeech(settings).synthesize(text)
    except Exception as exc:
        print(f"FPT TTS lỗi: {exc}")
        return

    print("FPT TTS gọi thành công.")
    print(f"- audio_url: {audio.audio_url or 'không có'}")


def _test_stt(settings: Settings, raw_path: str, language: str | None = None) -> None:
    path = Path(raw_path.strip('"').strip("'"))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists() or not path.is_file():
        print(f"\nKhông tìm thấy file âm thanh để test STT: {path}")
        return

    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    print(f"- language={language or settings.fpt_stt_language}")
    print(f"- file={path.name}")
    print("\nĐang gọi thử FPT.AI Whisper Speech-to-Text...")
    try:
        transcript = FPTSpeechToText(settings).transcribe(
            path.read_bytes(),
            content_type=content_type,
            filename=path.name,
            language=language,
        )
    except Exception as exc:
        print(f"FPT STT lỗi: {exc}")
        return

    print("FPT STT gọi thành công.")
    print(f"- transcript: {transcript.text or 'không nhận được nội dung'}")


def _test_llm(settings: Settings, text: str, stream: bool) -> None:
    print("\nĐang gọi thử SaoLa3.1-medium Chat Completions...")
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": text}],
        "temperature": 1,
        "max_tokens": 256,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "stream": stream,
    }
    print(f"- stream={stream}")
    request = urllib.request.Request(
        settings.llm_api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ChatbotDeepSearch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read()
            response_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        print(f"FPT LLM lỗi: HTTP {exc.code}: {detail or exc.reason}")
        return
    except urllib.error.URLError as exc:
        print(f"FPT LLM lỗi: không kết nối được: {exc.reason}")
        return

    try:
        content = extract_chat_response_content(response_body, response_type)
    except Exception as exc:
        print(f"FPT LLM loi: khong doc duoc response: {exc}")
        return
    print("FPT LLM gọi thành công.")
    print(f"- trả lời: {content[:500]}")


if __name__ == "__main__":
    main()
