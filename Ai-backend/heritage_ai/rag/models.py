"""Kiểu dữ liệu nội bộ của pipeline RAG."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDocument:
    content: str
    heritage_id: str
    heritage_name: str
    source: str
    document_name: str
    page: int | None = None
    section: str = ""
    intent: str = "all"
    source_url: str = ""
    file_path: str = ""


@dataclass(frozen=True)
class TextChunk:
    id: str
    content: str
    heritage_id: str
    heritage_name: str
    source: str
    document_name: str
    page: int | None
    section: str
    intent: str = "all"
    source_url: str = ""
    file_path: str = ""
