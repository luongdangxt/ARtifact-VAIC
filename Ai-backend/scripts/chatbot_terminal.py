from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.console import configure_utf8_console
from app.terminal_chatbot import TerminalChatbot


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Chạy Thư viện Di sản Thông minh trong terminal.")
    parser.add_argument("--no-tts", action="store_true", help="Không gọi Text-to-Speech.")
    parser.add_argument(
        "--log",
        default=None,
        help="File JSONL để ghi text thu được, câu trả lời và trạng thái TTS.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    log_path = None if args.log is None else Path(args.log)
    chatbot = TerminalChatbot(settings=settings, synthesize=not args.no_tts, log_path=log_path)
    chatbot.run()


if __name__ == "__main__":
    main()
