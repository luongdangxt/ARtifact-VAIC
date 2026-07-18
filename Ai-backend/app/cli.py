from __future__ import annotations

import argparse
import json

from .console import configure_utf8_console
from .config import Settings
from .ingest import ingest_documents
from .pipeline import SmartHeritageLibrary


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Thư viện Di sản Thông minh")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Hỏi bằng văn bản")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--no-tts", action="store_true")

    ingest_parser = subparsers.add_parser("ingest", help="Vector hóa PDF/TXT")
    ingest_parser.add_argument("--books-dir", default=None)

    args = parser.parse_args()
    settings = Settings.from_env()

    if args.command == "ask":
        pipeline = SmartHeritageLibrary.from_settings(settings)
        response = pipeline.ask_text(args.question, synthesize=not args.no_tts)
        print(json.dumps(response.to_public(), ensure_ascii=False, indent=2))
        return

    if args.command == "ingest":
        books_dir = settings.books_dir if args.books_dir is None else settings.root_dir / args.books_dir
        count = ingest_documents(
            books_dir=books_dir,
            vector_store_path=settings.vector_store_path,
            vector_collection_name=settings.vector_collection_name,
            chunk_size_words=settings.chunk_size_words,
            chunk_overlap_words=settings.chunk_overlap_words,
        )
        print(f"Đã ingest {count} đoạn vào ChromaDB {settings.vector_store_path} / {settings.vector_collection_name}")
        return


if __name__ == "__main__":
    main()
