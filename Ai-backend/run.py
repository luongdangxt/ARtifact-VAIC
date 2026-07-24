"""Điểm khởi chạy chatbot Nghệ nhân AI (chỉ văn bản)."""

from __future__ import annotations

import argparse
import os
import sys


def configure_utf8_console() -> None:
    """Dùng UTF-8 cho terminal Windows để hiển thị/nhập tiếng Việt đúng."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except (AttributeError, OSError):
            pass

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_utf8_console()

from heritage_ai.orchestrator import HeritageChatbot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nghệ nhân AI giới thiệu di sản văn hóa phi vật thể Việt Nam."
    )
    parser.add_argument(
        "-q",
        "--query",
        help="Gửi một câu hỏi và thoát. Nếu bỏ trống, chương trình chạy tương tác.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Liệt kê các di sản đang có trong kho tri thức.",
    )
    return parser


def run_interactive(chatbot: HeritageChatbot) -> None:
    print("Nghệ nhân AI — Trợ lý di sản văn hóa phi vật thể")
    print("Gõ 'danhsach' để xem các di sản, hoặc 'thoat' để kết thúc.\n")

    while True:
        try:
            query = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHẹn gặp lại bạn!")
            break

        if not query:
            continue
        if query.casefold() in {"thoat", "exit", "quit"}:
            print("Hẹn gặp lại bạn!")
            break
        if query.casefold() in {"danhsach", "danh sach", "list"}:
            print(chatbot.list_heritages())
            continue

        print(f"\nNghệ nhân AI:\n{chatbot.ask(query)}\n")


def main() -> None:
    args = build_parser().parse_args()
    chatbot = HeritageChatbot()

    if args.list:
        print(chatbot.list_heritages())
        return
    if args.query:
        print(chatbot.ask(args.query))
        return

    run_interactive(chatbot)


if __name__ == "__main__":
    main()
