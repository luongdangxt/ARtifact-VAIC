from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import textwrap
import time

from .audio_playback import play_audio_file
from .audio_recording import record_wav
from .config import Settings
from .embeddings import strip_vietnamese_accents
from .models import PipelineResponse
from .pipeline import SmartHeritageLibrary


STOP_VOICE_PHRASES = {
    "dung lai",
    "dung",
    "ket thuc",
    "thoat",
    "tam biet",
    "stop",
    "exit",
    "quit",
}


class TerminalChatbot:
    def __init__(
        self,
        settings: Settings,
        synthesize: bool = True,
        log_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.pipeline = SmartHeritageLibrary.from_settings(settings)
        self.synthesize = synthesize
        self.log_path = log_path or settings.root_dir / "logs" / "terminal_chatbot.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        self._print_banner()
        while True:
            print("\nNhập câu hỏi, hoặc gõ /help, /audio, /reload, /exit")
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nHẹn gặp lại!!")
                return

            if not raw:
                continue
            lowered = raw.lower()
            if lowered in {"/exit", "exit", "quit", "/quit"}:
                print("Tạm biệt.")
                return
            if lowered == "/reload":
                print("Đang tải lại kho vector...")
                self.pipeline = SmartHeritageLibrary.from_settings(self.settings)
                print("Đã tải lại.")
                continue
            if lowered == "/help":
                self._print_help()
                continue
            if lowered == "/audio":
                self.voice_chat_loop()
                continue
            if lowered.startswith("/audio "):
                print("Chế độ giọng nói không nhận file hoặc tham số nữa. Gõ /audio để bắt đầu trò chuyện 1-1.")
                continue

            self.ask_text(raw)

    def ask_text(
        self,
        question: str,
        transcript: str | None = None,
        force_speak: bool = False,
    ) -> PipelineResponse:
        self._write_log("collected_text", {"text": question, "transcript": transcript})
        response = self.pipeline.ask_text(question, synthesize=False, transcript=transcript)

        if not response.allowed:
            print(f"Nghệ nhân AI: {response.answer}")
            self._write_log("refusal", response.to_public())
            if force_speak:
                print("[🔊] Nghệ nhân AI đang đọc câu trả lời...")
                self._speak(response.answer)
            return response

        print("\nNghệ nhân AI:")
        print(self._wrap(response.answer))
        self._print_sources(response.sources)
        self._write_log("answer", response.to_public())

        if self.synthesize or force_speak:
            if force_speak:
                print("[🔊] Nghệ nhân AI đang đọc câu trả lời...")
            self._speak(response.answer)

        return response

    def voice_chat_loop(self) -> None:
        print("\nNghệ nhân AI — Chế độ Trò chuyện bằng Giọng nói")
        print("Nói 'Dừng lại' hoặc bấm Ctrl+C để kết thúc.\n")

        path = self.settings.root_dir / "logs" / "recordings" / "last_microphone.wav"
        while True:
            try:
                print("\n[🎙️] Đang điều chỉnh tạp âm, vui lòng đợi 1 giây...")
                time.sleep(1)
                print("[🎙️] Nghệ nhân AI đang lắng nghe... Mời bạn nói.")
                record_wav(path, self.settings.audio_record_seconds, self.settings.audio_sample_rate)

                print("[⏳] Đang xử lý giọng nói...")
                transcript = self.pipeline.stt.transcribe(
                    path.read_bytes(),
                    content_type="audio/wav",
                    filename=path.name,
                    language=self.settings.fpt_stt_language,
                )
            except KeyboardInterrupt:
                print("\nHẹn gặp lại!!")
                return
            except Exception as exc:
                print(f"Không xử lý được giọng nói: {exc}")
                self._write_log("voice_error", {"error": str(exc)})
                continue

            print(f"Bạn vừa nói: {transcript.text}")
            self._write_log(
                "transcript",
                {
                    "provider": transcript.provider,
                    "request_id": transcript.request_id,
                    "text": transcript.text,
                },
            )

            if self._is_stop_voice_phrase(transcript.text):
                print("Đã kết thúc chế độ trò chuyện bằng giọng nói.")
                return

            self.ask_text(transcript.text, transcript=transcript.text, force_speak=True)

    def _speak(self, text: str) -> None:
        try:
            audio = self.pipeline.tts.synthesize(text)
            if audio.audio_url:
                print(f"Âm thanh: {audio.audio_url}")
                self._play_if_local(audio.audio_url)
            else:
                print("Âm thanh: chưa tạo được file âm thanh.")
            self._write_log(
                "tts",
                {
                    "provider": audio.provider,
                    "audio_url": audio.audio_url,
                    "request_id": audio.request_id,
                },
            )
        except Exception as exc:
            print(f"Âm thanh: không tạo được âm thanh. {exc}")
            self._write_log("tts_error", {"error": str(exc)})

    def _play_if_local(self, audio_url: str) -> None:
        if not self.settings.tts_autoplay:
            print("[TTS_AUTOPLAY=false] Chi luu file am thanh, khong phat tu dong.")
            return
        path = Path(audio_url)
        if not path.exists():
            print(f"Khong tim thay file am thanh de phat: {path}")
            return
        try:
            print("[PLAY] Dang phat cau tra loi bang giong noi...")
            play_audio_file(path)
            print("[OK] Da phat xong cau tra loi.")
        except Exception as exc:
            print(f"Không phát được âm thanh: {exc}")

    def _write_log(self, event: str, payload: dict) -> None:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": payload,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _print_sources(sources: list) -> None:
        if not sources:
            print("\nNguồn tham khảo: Không tìm thấy đoạn tư liệu phù hợp.")
            return
        labels = []
        for source in sources[:5]:
            page = f", trang {source.page}" if source.page else ""
            labels.append(f"{source.source}{page}")
        print("\nNguồn tham khảo:")
        for label in labels:
            print(f"- {label}")

    @staticmethod
    def _wrap(text: str) -> str:
        paragraphs = text.splitlines() or [text]
        return "\n".join(textwrap.fill(paragraph, width=100) if paragraph else "" for paragraph in paragraphs)

    @staticmethod
    def _is_stop_voice_phrase(text: str) -> bool:
        normalized = strip_vietnamese_accents(text.lower())
        normalized = " ".join(normalized.split())
        return any(phrase in normalized for phrase in STOP_VOICE_PHRASES)

    @staticmethod
    def _print_banner() -> None:
        print("=" * 72)
        print("THƯ VIỆN DI SẢN THÔNG MINH - TERMINAL CHATBOT")
        print("=" * 72)
        print("Gõ câu hỏi và nhấn Enter để bắt đầu.")

    @staticmethod
    def _print_help() -> None:
        print("Lệnh hỗ trợ:")
        print("  /audio         Mở chế độ trò chuyện bằng giọng nói 1-1.")
        print("  /reload        Tải lại vector store sau khi ingest PDF mới.")
        print("  /exit          Thoát chatbot.")
