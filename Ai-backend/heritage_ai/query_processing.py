"""Semantic Router (local, có LLM dự phòng) và bước Reflection."""

from __future__ import annotations

import logging
import os

from heritage_ai.llm_client import LlmClient
from heritage_ai.local_router import LocalRouter
from heritage_ai.models import QueryContext
from heritage_ai.text_utils import normalize_text

_log = logging.getLogger(__name__)

# local  = chỉ router local (nhanh nhất, câu mơ hồ thì hỏi lại du khách)
# auto   = local trước, mơ hồ mới nhờ LLM phân giải  (mặc định)
# gemini = luôn gọi LLM như trước khi tối ưu (để đối chiếu khi gỡ lỗi)
DEFAULT_MODE = "auto"


class QueryProcessor:
    def __init__(
        self,
        gemini: LlmClient,
        router: LocalRouter | None = None,
        mode: str | None = None,
    ) -> None:
        self.gemini = gemini
        self.router = router or LocalRouter()
        self.mode = (mode or os.getenv("ROUTER_MODE", DEFAULT_MODE)).strip().lower()

    def process(
        self, query: str, ranked: list[tuple[str, float]]
    ) -> QueryContext:
        """`ranked`: (tên di sản, score) từ vector search, xếp từ khớp nhất."""
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

        analysis = None
        if self.mode != "gemini":
            analysis = self.router.route(query, ranked)
            if analysis is None:
                _log.info("Router local chưa chắc chắn về di sản: %r", query)

        if analysis is None:
            if self.mode == "local":
                return QueryContext(
                    original_query=query.strip(),
                    normalized_query=normalized,
                    intent="overview",
                    needs_clarification=True,
                    clarification_question="Bạn muốn tìm hiểu về di sản nào?",
                )
            analysis = self.gemini.analyze_query(query, [name for name, _ in ranked])

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
