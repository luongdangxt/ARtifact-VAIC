"""Điều phối toàn bộ pipeline hỏi đáp."""

from __future__ import annotations

from heritage_ai.gemini_client import GeminiClient, GeminiError
from heritage_ai.query_processing import QueryProcessor
from heritage_ai.rag.retriever import RagRetriever
from heritage_ai.rag.vector_store import RagError
from heritage_ai.report_agent import TextReportAgent
from heritage_ai.repository import HeritageRepository
from heritage_ai.research_agents import ResearchSupervisor


class HeritageChatbot:
    def __init__(
        self,
        repository: HeritageRepository | None = None,
        gemini: GeminiClient | None = None,
        retriever: RagRetriever | None = None,
    ) -> None:
        self.repository = repository or HeritageRepository()
        self.gemini = gemini or GeminiClient()
        self.query_processor = QueryProcessor(self.gemini)
        self.retriever = retriever or RagRetriever(self.gemini)
        self.supervisor = ResearchSupervisor(self.retriever)
        self.report_agent = TextReportAgent(self.gemini)

    def ask(self, query: str) -> str:
        if query.strip():
            try:
                heritage_names = self.retriever.candidate_heritage_names(query)
            except RagError as exc:
                return f"Không thể nhận diện di sản từ kho RAG: {exc}"
            except GeminiError as exc:
                return f"Không thể tạo embedding để nhận diện di sản: {exc}"
        else:
            heritage_names = [item["name"] for item in self.repository.all()]
        if query.strip() and not heritage_names:
            return "Tôi chưa tìm thấy di sản phù hợp trong kho dữ liệu."
        try:
            context = self.query_processor.process(query, heritage_names)
        except GeminiError as exc:
            return f"Không thể xử lý câu hỏi bằng Gemini: {exc}"

        reflection = self.query_processor.reflect(context)
        if reflection:
            return reflection

        heritage = self.repository.find(context.heritage_name or context.normalized_query)
        if heritage is None:
            names = ", ".join(item["name"] for item in self.repository.all())
            return (
                "Tôi chưa xác định được di sản bạn muốn tìm hiểu. "
                f"Hiện tôi có dữ liệu về: {names}. "
                "Bạn hãy nhắc rõ tên di sản trong câu hỏi nhé."
            )

        try:
            research_result = self.supervisor.run(context, heritage)
            return self.report_agent.compose(context, research_result)
        except RagError as exc:
            return f"Không thể truy xuất kho RAG: {exc}"
        except GeminiError as exc:
            return f"Không thể tạo lời kể bằng Gemini: {exc}"

    def list_heritages(self) -> str:
        lines = ["Các di sản hiện có trong kho tri thức:"]
        lines.extend(
            f"{index}. {item['name']}"
            for index, item in enumerate(self.repository.all(), start=1)
        )
        return "\n".join(lines)
