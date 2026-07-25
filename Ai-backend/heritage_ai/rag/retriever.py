"""Truy xuất các đoạn tư liệu phù hợp với câu hỏi và intent."""

from __future__ import annotations

import os
from pathlib import Path

from heritage_ai.gemini_client import GeminiClient
from heritage_ai.models import Evidence
from heritage_ai.rag.embedding_client import LocalEmbedder, LocalEmbeddingError
from heritage_ai.rag.vector_store import (
    ChromaVectorStore,
    RagError,
    RagNoEvidenceError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RagRetriever:
    INTENT_HINTS = {
        "overview": "khái quát và những đặc điểm tiêu biểu",
        "history": "nguồn gốc, quá trình hình thành và lịch sử",
        "practice": "cách thực hành, trình diễn và truyền dạy",
        "meaning": "ý nghĩa và giá trị văn hóa",
        "etiquette": "lưu ý ứng xử dành cho du khách",
        "location": "không gian văn hóa và địa bàn thực hành",
    }

    def __init__(
        self,
        gemini: GeminiClient | None = None,
        vector_store: ChromaVectorStore | None = None,
        embedder: LocalEmbedder | None = None,
        top_k: int | None = None,
        min_relevance: float | None = None,
    ) -> None:
        # `gemini` được giữ trong chữ ký để tương thích với code gọi cũ; embedding
        # giờ chạy hoàn toàn local.
        self.embedder = embedder or LocalEmbedder()
        self.vector_store = vector_store or ChromaVectorStore(
            PROJECT_ROOT / "storage" / "chroma",
            embedding_model=self.embedder.model,
        )
        self.top_k = top_k or int(os.getenv("RAG_TOP_K", "5"))
        self.min_relevance = (
            min_relevance
            if min_relevance is not None
            else float(os.getenv("RAG_MIN_RELEVANCE", "0.15"))
        )

    def retrieve(
        self, query: str, heritage_id: str, intent: str
    ) -> list[Evidence]:
        intent_hint = self.INTENT_HINTS.get(intent, self.INTENT_HINTS["overview"])
        enriched_query = f"{query}\nNội dung cần tìm: {intent_hint}."
        try:
            query_embedding = self.embedder.embed_query(enriched_query)
        except LocalEmbeddingError as exc:
            raise RagError(str(exc)) from exc
        evidence = self.vector_store.search(
            query_embedding=query_embedding,
            heritage_id=heritage_id,
            intent=intent,
            top_k=self.top_k,
            min_relevance=self.min_relevance,
        )
        if not evidence:
            raise RagNoEvidenceError(
                "Không tìm thấy tư liệu đủ liên quan trong kho RAG cho câu hỏi này."
            )
        return evidence

    def candidate_heritage_names(self, query: str, limit: int = 8) -> list[str]:
        try:
            query_embedding = self.embedder.embed_query(query)
        except LocalEmbeddingError as exc:
            raise RagError(str(exc)) from exc
        names = self.vector_store.candidate_heritage_names(
            query_embedding=query_embedding,
            top_k=max(20, limit * 3),
        )
        return names[:limit]
