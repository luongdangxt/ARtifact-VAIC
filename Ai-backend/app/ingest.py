from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .chunking import chunk_text, normalize_text
from .models import DocumentChunk
from .qa_pairs import extract_qa_pairs
from .vector_store import ChromaVectorStore


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def iter_source_files(*directories: Path) -> Iterable[Path]:
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path


def iter_source_paths(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from iter_source_files(path)
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def extract_pages(path: Path) -> Iterable[tuple[int | None, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Cần cài pypdf để đọc PDF: pip install pypdf") from exc

        reader = PdfReader(str(path))
        for index, page in enumerate(reader.pages, start=1):
            yield index, normalize_text(page.extract_text() or "")
        return

    text = normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    yield None, text


def build_chunks(
    files: Iterable[Path],
    chunk_size_words: int = 260,
    chunk_overlap_words: int = 60,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for path in files:
        for page, text in extract_pages(path):
            for index, chunk in enumerate(chunk_text(text, chunk_size_words, chunk_overlap_words), start=1):
                digest = hashlib.sha1(
                    f"{path.name}:{page}:{index}:{chunk[:120]}".encode("utf-8")
                ).hexdigest()[:16]
                chunks.append(
                    DocumentChunk(
                        id=digest,
                        text=chunk,
                        metadata={
                            "source": path.name,
                            "title": path.stem,
                            "page": page,
                            "chunk_index": index,
                        },
                    )
                )

            # Keep every PDF question-answer pair intact. PDF chunk boundaries
            # can otherwise separate the question from its answer.
            for qa_index, pair in enumerate(extract_qa_pairs(text), start=1):
                qa_text = f"Câu hỏi: {pair.question}\nĐáp án: {pair.answer}"
                digest = hashlib.sha1(
                    f"{path.name}:{page}:qa:{qa_index}:{qa_text}".encode("utf-8")
                ).hexdigest()[:16]
                chunks.append(
                    DocumentChunk(
                        id=digest,
                        text=qa_text,
                        metadata={
                            "source": path.name,
                            "title": path.stem,
                            "page": page,
                            "chunk_index": qa_index,
                            "content_type": "qa_pair",
                        },
                    )
                )
    return chunks


def ingest_documents(
    books_dir: Path,
    vector_store_path: Path,
    vector_collection_name: str = "heritage_chunks",
    chunk_size_words: int = 260,
    chunk_overlap_words: int = 60,
) -> int:
    directories = [books_dir]

    files = list(iter_source_files(*directories))
    chunks = build_chunks(files, chunk_size_words, chunk_overlap_words)
    store = ChromaVectorStore(vector_store_path, vector_collection_name)
    return store.rebuild(chunks)


def ingest_document_paths(
    paths: Iterable[Path],
    vector_store_path: Path,
    vector_collection_name: str = "heritage_chunks",
    chunk_size_words: int = 260,
    chunk_overlap_words: int = 60,
) -> int:
    files = list(iter_source_paths(paths))
    chunks = build_chunks(files, chunk_size_words, chunk_overlap_words)
    store = ChromaVectorStore(vector_store_path, vector_collection_name)
    return store.rebuild(chunks)
