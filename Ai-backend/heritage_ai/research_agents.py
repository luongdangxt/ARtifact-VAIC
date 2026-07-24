"""Supervisor truy xuất RAG và agent kiểm chứng evidence."""

from __future__ import annotations

from heritage_ai.models import QueryContext, ResearchResult
from heritage_ai.rag.retriever import RagRetriever


class VerificationAgent:
    REQUIRED_FIELDS = {"id", "name"}

    def verify(self, result: ResearchResult) -> ResearchResult:
        missing = self.REQUIRED_FIELDS - set(result.heritage)
        if missing:
            result.warnings.append(
                "Bản ghi đang thiếu dữ liệu: " + ", ".join(sorted(missing))
            )
        if not result.evidence:
            result.warnings.append("Không tìm thấy bằng chứng phù hợp với câu hỏi.")
        elif any(not evidence.source.strip() for evidence in result.evidence):
            result.warnings.append("Có đoạn tư liệu chưa xác định được nguồn.")

        result.verified = not result.warnings
        return result


class ResearchSupervisor:
    """Điều phối truy xuất vector và kiểm chứng kết quả."""

    def __init__(self, retriever: RagRetriever) -> None:
        self.retriever = retriever
        self.verifier = VerificationAgent()

    def run(self, context: QueryContext, heritage: dict) -> ResearchResult:
        result = ResearchResult(heritage=heritage, intent=context.intent)
        result.evidence = self.retriever.retrieve(
            query=context.original_query,
            heritage_id=heritage["id"],
            intent=context.intent,
        )
        return self.verifier.verify(result)
