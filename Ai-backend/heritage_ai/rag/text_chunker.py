"""Chia tài liệu thành các đoạn có chồng lấn để tạo embedding."""

from __future__ import annotations

import hashlib

from heritage_ai.rag.models import SourceDocument, TextChunk


class TextChunker:
    def __init__(self, max_words: int = 320, overlap_words: int = 50) -> None:
        if max_words <= 0:
            raise ValueError("max_words phải lớn hơn 0.")
        if overlap_words < 0 or overlap_words >= max_words:
            raise ValueError("overlap_words phải từ 0 đến nhỏ hơn max_words.")
        self.max_words = max_words
        self.overlap_words = overlap_words

    def split(self, documents: list[SourceDocument]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for document in documents:
            words = document.content.split()
            if not words:
                continue
            step = self.max_words - self.overlap_words
            for index, start in enumerate(range(0, len(words), step)):
                content = " ".join(words[start : start + self.max_words]).strip()
                if not content:
                    continue
                chunks.append(self._make_chunk(document, content, index))
                if start + self.max_words >= len(words):
                    break
        return chunks

    @staticmethod
    def _make_chunk(
        document: SourceDocument, content: str, index: int
    ) -> TextChunk:
        identity = "|".join(
            (
                document.file_path,
                document.heritage_id,
                str(document.page),
                document.section,
                document.intent,
                str(index),
                content,
            )
        )
        chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return TextChunk(
            id=chunk_id,
            content=content,
            heritage_id=document.heritage_id,
            heritage_name=document.heritage_name,
            source=document.source,
            document_name=document.document_name,
            page=document.page,
            section=document.section,
            intent=document.intent,
            source_url=document.source_url,
            file_path=document.file_path,
        )
