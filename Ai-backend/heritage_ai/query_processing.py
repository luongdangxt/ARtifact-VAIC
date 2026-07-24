"""Semantic Router dùng Gemini và bước Reflection."""

from __future__ import annotations

from heritage_ai.gemini_client import GeminiClient
from heritage_ai.models import QueryContext
from heritage_ai.text_utils import normalize_text


class QueryProcessor:
    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini

    def process(self, query: str, heritage_names: list[str]) -> QueryContext:
        normalized = normalize_text(query)
        if not normalized:
            return QueryContext(
                original_query="",
                normalized_query="",
                intent="overview",
                needs_clarification=True,
                clarification_question=(
                    "Bạn hãy nhập câu hỏi hoặc tên một di sản muốn tìm hiểu."
                ),
            )

        analysis = self.gemini.analyze_query(query, heritage_names)

        return QueryContext(
            original_query=query.strip(),
            normalized_query=normalized,
            intent=analysis.intent,
            requested_length=analysis.requested_length,
            heritage_name=analysis.heritage_name,
            needs_clarification=analysis.needs_clarification,
            clarification_question=analysis.clarification_question,
        )

    def reflect(self, context: QueryContext) -> str | None:
        """Trả về gợi ý khi câu hỏi chưa đủ thông tin để nghiên cứu."""
        if context.needs_clarification:
            return context.clarification_question
        return None
