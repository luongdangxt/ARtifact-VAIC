"""Agent chuyển kết quả nghiên cứu thành lời kể dạng văn bản."""

from __future__ import annotations

import logging
import re

from heritage_ai.llm_client import LlmClient
from heritage_ai.models import QueryContext, ResearchResult

_log = logging.getLogger(__name__)

# Mã trích dẫn [1], [2]... trong lời kể. Vẫn yêu cầu LLM gắn để bám sát tư liệu,
# nhưng cắt trước khi trả về vì mục "Nguồn tham khảo" không còn hiển thị nữa.
# Phải nuốt cả dấu phân cách GIỮA các mã liền nhau: một câu dẫn hai nguồn được viết
# "... tinh tế [1], [2]." — xóa riêng từng mã sẽ để lại "... tinh tế,." và TTS đọc
# thành một quãng ngắt cụt lủn.
_CITATION_RE = re.compile(r"\s*\[\d+\](?:\s*[,;]\s*\[\d+\])*")

# LLM không đếm từ chính xác nên prompt "tối đa 150 từ" thi thoảng vẫn tràn;
# cắt cứng tại ranh giới câu để không bao giờ vượt xa trần sản phẩm.
_MAX_ANSWER_WORDS = 160
_SENTENCE_END_RE = re.compile(r"[.!?…](?=\s|$)")


def _trim_to_sentence(text: str, max_words: int = _MAX_ANSWER_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    clipped = " ".join(words[:max_words])
    ends = list(_SENTENCE_END_RE.finditer(clipped))
    if ends:
        return clipped[: ends[-1].end()]
    return clipped + "…"


class TextReportAgent:
    def __init__(self, gemini: LlmClient) -> None:
        self.gemini = gemini

    def compose(
        self,
        context: QueryContext,
        result: ResearchResult,
        asked: list[str] | None = None,
        history: list[dict] | None = None,
    ) -> str:
        heritage = result.heritage
        body = self.gemini.generate_report(
            query=context.original_query,
            heritage_name=heritage["name"],
            evidence=result.evidence,
            requested_length=context.requested_length,
            history=history,
        )

        if result.warnings:
            # Cảnh báo kiểm chứng chỉ để vận hành xem log, không đẩy ra giao diện/TTS.
            _log.info(
                "Cảnh báo kiểm chứng (%s): %s",
                heritage.get("name", "?"),
                " ".join(result.warnings),
            )

        answer = _trim_to_sentence(_CITATION_RE.sub("", body).strip())

        history = list(asked or [])
        history.append(context.original_query)
        questions = self._follow_ups(heritage, history)
        if questions:
            follow_ups = "\n".join(f"- {question}" for question in questions)
            answer += f"\n\nBạn có thể hỏi tiếp:\n{follow_ups}"
        return answer

    @staticmethod
    def _follow_ups(heritage: dict, asked: list[str]) -> list[str]:
        """Gợi ý lấy từ danh sách CÓ SẴN của di sản, bỏ câu du khách đã hỏi.

        Cố ý KHÔNG để LLM tự nghĩ câu hỏi: câu sinh động hay chạm tới khía cạnh
        không có trong tư liệu, du khách bấm vào lại nhận "tư liệu không đề cập".
        """
        seen = {question.strip().casefold() for question in asked}
        return [
            question
            for question in heritage.get("follow_up_questions", [])
            if question.strip().casefold() not in seen
        ]
