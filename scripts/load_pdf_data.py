from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.console import configure_utf8_console
from app.ingest import extract_pages, ingest_document_paths, iter_source_paths
from app.pipeline import SmartHeritageLibrary


QUESTION_RE = re.compile(r"([^.\n!?]*(?:\?|？))")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(
        description="Nạp file PDF/TXT vào vector store và hỏi dữ liệu ngay trên terminal."
    )
    parser.add_argument("--pdf", action="append", default=[], help="Đường dẫn PDF/TXT cần nạp. Có thể dùng nhiều lần.")
    parser.add_argument("--folder", action="append", default=[], help="Thư mục chứa nhiều PDF/TXT.")
    parser.add_argument("--question", action="append", default=[], help="Câu hỏi cần chạy sau khi nạp dữ liệu.")
    parser.add_argument("--questions-file", default=None, help="File .txt chứa danh sách câu hỏi, mỗi dòng một câu.")
    parser.add_argument(
        "--extract-questions-from-pdf",
        action="store_true",
        help="Tự tìm các câu kết thúc bằng dấu ? trong PDF/TXT vừa nạp và trả lời.",
    )
    parser.add_argument("--no-tts", action="store_true", help="Không gọi Text-to-Speech khi trả lời batch.")
    args = parser.parse_args()

    settings = Settings.from_env()
    source_paths = [_resolve_path(item) for item in args.pdf + args.folder]
    if not source_paths:
        source_paths = [settings.books_dir]

    print("Đang nạp dữ liệu PDF/TXT vào vector database...")
    count = ingest_document_paths(
        source_paths,
        vector_store_path=settings.vector_store_path,
        vector_collection_name=settings.vector_collection_name,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
    )
    print(f"Đã nạp {count} đoạn vào ChromaDB {settings.vector_store_path} / {settings.vector_collection_name}")

    questions = list(args.question)
    if args.questions_file:
        questions.extend(_read_questions_file(_resolve_path(args.questions_file)))
    if args.extract_questions_from_pdf:
        questions.extend(_extract_questions(source_paths))

    if not questions:
        print("Chưa có câu hỏi. Hãy chạy thêm --question hoặc --questions-file.")
        print("Hoặc mở chatbot terminal bằng: python scripts\\chatbot_terminal.py")
        return

    pipeline = SmartHeritageLibrary.from_settings(settings)
    log_path = settings.root_dir / "logs" / "pdf_answers.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    for index, question in enumerate(questions, start=1):
        question = question.strip()
        if not question:
            continue
        print(f"\nCâu hỏi {index}: {question}")
        response = pipeline.ask_text(question, synthesize=False)
        print("Nghệ Nhân AI:")
        print(response.answer)
        if response.sources:
            print("Nguồn: " + "; ".join(source.title for source in response.sources[:3]))
        if not args.no_tts and response.allowed:
            try:
                audio = pipeline.tts.synthesize(response.answer)
                print(f"Âm thanh: {audio.audio_url or 'chưa có FPT_API_KEY'}")
            except Exception as exc:
                print(f"Âm thanh: không tạo được âm thanh. {exc}")

        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "question": question,
                        "response": response.to_public(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"\nLog: đã ghi kết quả batch vào {log_path}")


def _resolve_path(raw: str) -> Path:
    path = Path(raw.strip('"').strip("'"))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _read_questions_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy questions-file: {path}")
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _extract_questions(paths: list[Path]) -> list[str]:
    questions: list[str] = []
    for file_path in iter_source_paths(paths):
        for _, text in extract_pages(file_path):
            for match in QUESTION_RE.findall(text):
                question = match.strip()
                if len(question) >= 8:
                    questions.append(question)
    return questions


if __name__ == "__main__":
    main()
