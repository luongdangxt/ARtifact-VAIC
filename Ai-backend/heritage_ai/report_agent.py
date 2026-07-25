"""Agent chuyển kết quả nghiên cứu thành lời kể dạng văn bản."""

from __future__ import annotations

import re

from heritage_ai.gemini_client import GeminiClient
from heritage_ai.models import QueryContext, ResearchResult


class TextReportAgent:
    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini

    def compose(self, context: QueryContext, result: ResearchResult) -> str:
        heritage = result.heritage
        body = self.gemini.generate_report(
            query=context.original_query,
            heritage_name=heritage["name"],
            evidence=result.evidence,
            requested_length=context.requested_length,
        )

        notes = ""
        if result.warnings:
            notes = "\n\nLưu ý kiểm chứng: " + " ".join(result.warnings)

        cited_indexes = {
            int(value)
            for value in re.findall(r"\[(\d+)\]", body)
            if 1 <= int(value) <= len(result.evidence)
        }
        source_items = (
            [
                (index, result.evidence[index - 1])
                for index in sorted(cited_indexes)
            ]
            if cited_indexes
            else list(enumerate(result.evidence, start=1))
        )
        sources = "\n".join(
            self._format_source(index, evidence)
            for index, evidence in source_items
        )
        follow_ups = "\n".join(
            f"- {question}" for question in heritage.get("follow_up_questions", [])
        )

        return (
            f"{body}{notes}\n\n"
            f"Nguồn tham khảo:\n{sources}\n\n"
            f"Bạn có thể hỏi tiếp:\n{follow_ups}\n\n"
            "Lưu ý: đây là nhân vật AI tổng hợp tư liệu, không phải lời nói trực tiếp "
            "của một nghệ nhân cụ thể."
        )

    @staticmethod
    def _format_source(index: int, evidence) -> str:
        details = [evidence.source]
        if evidence.document_name:
            details.append(evidence.document_name)
        if evidence.page:
            details.append(f"trang {evidence.page}")
        if evidence.title:
            details.append(f"mục {evidence.title}")
        label = ", ".join(details)
        if evidence.source_url:
            label += f" — {evidence.source_url}"
        return f"[{index}] {label}"
