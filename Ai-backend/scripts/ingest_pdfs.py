from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.console import configure_utf8_console
from app.config import Settings
from app.ingest import ingest_documents


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Băm nhỏ và vector hóa kho sách PDF/TXT.")
    parser.add_argument("--books-dir", default=None, help="Thư mục chứa PDF/TXT. Mặc định: data/books")
    args = parser.parse_args()

    settings = Settings.from_env()
    books_dir = settings.books_dir if args.books_dir is None else (settings.root_dir / args.books_dir)
    count = ingest_documents(
        books_dir=books_dir,
        vector_store_path=settings.vector_store_path,
        vector_collection_name=settings.vector_collection_name,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
    )
    print(f"Đã ingest {count} đoạn vào ChromaDB {settings.vector_store_path} / {settings.vector_collection_name}")


if __name__ == "__main__":
    main()
