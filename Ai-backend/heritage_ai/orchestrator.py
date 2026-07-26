"""Điều phối toàn bộ pipeline hỏi đáp."""

from __future__ import annotations

import logging
import re

from heritage_ai.llm_client import LlmClient
from heritage_ai.llm_contract import LlmError
from heritage_ai.local_router import is_system_probe
from heritage_ai.models import QueryContext
from heritage_ai.query_processing import QueryProcessor
from heritage_ai.rag.retriever import RagRetriever
from heritage_ai.rag.vector_store import RagError, RagNoEvidenceError
from heritage_ai.report_agent import TextReportAgent
from heritage_ai.repository import HeritageRepository
from heritage_ai.research_agents import ResearchSupervisor
from heritage_ai.text_utils import normalize_text

_log = logging.getLogger(__name__)

# Mọi lỗi kỹ thuật đều trả về đúng MỘT câu chung chung: chi tiết (Gemini, RAG,
# embedding...) chỉ được ghi log — lộ ra giao diện/TTS là lộ nội bộ hệ thống.
TROUBLE_MESSAGE = "Xin lỗi, tôi đang gặp chút trục trặc, bạn thử hỏi lại giúp nhé."
NO_EVIDENCE_MESSAGE = "Xin lỗi, tôi chưa có tư liệu về điều này."
SYSTEM_PROBE_MESSAGE = (
    "Tôi chỉ có thể chia sẻ về di sản văn hóa thôi, bạn hỏi tôi về {topic} nhé."
)

# Marker do api._build_query chèn vào cuối câu hỏi để neo di sản của nghệ nhân.
_CRAFT_MARKER_RE = re.compile(r"\(Bối cảnh di sản: (?P<craft>[^)]+)\)")


class HeritageChatbot:
    def __init__(
        self,
        repository: HeritageRepository | None = None,
        gemini: LlmClient | None = None,
        retriever: RagRetriever | None = None,
    ) -> None:
        self.repository = repository or HeritageRepository()
        # Tên `gemini` giữ nguyên cho code gọi cũ, nhưng bên trong là LlmClient:
        # Gemini chính + gpt-oss-120b (FPT) dự phòng khi Gemini hỏng/hết quota.
        self.gemini = gemini or LlmClient()
        self.query_processor = QueryProcessor(self.gemini)
        self.retriever = retriever or RagRetriever(self.gemini)
        self.supervisor = ResearchSupervisor(self.retriever)
        self.report_agent = TextReportAgent(self.gemini)

    def ask(
        self,
        query: str,
        asked: list[str] | None = None,
        history: list[dict] | None = None,
    ) -> str:
        """`asked`: các câu du khách đã hỏi trước đó — chỉ dùng để câu hỏi gợi ý
        cuối lời kể không mời hỏi lại điều vừa trả lời.
        `history`: vài lượt hội thoại gần nhất ({"role", "content"}) — chỉ dùng để
        hiểu câu hỏi nối tiếp (đại từ, câu cụt), không được lặp lại vào trả lời."""
        if query.strip() and is_system_probe(normalize_text(query)):
            return SYSTEM_PROBE_MESSAGE.format(topic=self._probe_topic(query))
        if query.strip():
            try:
                ranked = self.retriever.rank_heritage_names(query)
            except (RagError, LlmError) as exc:
                _log.warning("Không xếp hạng được di sản cho %r: %s", query, exc)
                return TROUBLE_MESSAGE
        else:
            ranked = [(item["name"], 0.0) for item in self.repository.all()]
        if query.strip() and not ranked:
            return "Tôi chưa tìm thấy di sản phù hợp trong kho dữ liệu."
        try:
            context = self.query_processor.process(query, ranked)
            if context.needs_clarification:
                context = self._resolve_with_history(query, context, history)
        except LlmError as exc:
            _log.warning("Không phân tích được câu hỏi %r: %s", query, exc)
            return TROUBLE_MESSAGE

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
            return self.report_agent.compose(
                context, research_result, asked or [], history or []
            )
        except RagNoEvidenceError:
            return NO_EVIDENCE_MESSAGE
        except (RagError, LlmError) as exc:
            _log.warning(
                "Không tạo được lời kể cho %r (%s): %s",
                query,
                heritage.get("name", "?"),
                exc,
            )
            return TROUBLE_MESSAGE

    def _probe_topic(self, query: str) -> str:
        """Tên di sản để mời hỏi tiếp trong câu từ chối: lấy từ marker bối cảnh
        do API chèn; không có thì mời chung chung."""
        match = _CRAFT_MARKER_RE.search(query)
        if match:
            return match.group("craft").strip()
        return "các di sản văn hóa"

    def _resolve_with_history(
        self,
        query: str,
        context: QueryContext,
        history: list[dict] | None,
    ) -> QueryContext:
        """Câu hỏi nối tiếp mơ hồ ("thế nó có từ bao giờ?") thì ghép câu du khách
        hỏi gần nhất vào để nhận diện lại di sản, thay vì hỏi ngược du khách."""
        previous = next(
            (
                str(turn.get("content", "")).strip()
                for turn in reversed(history or [])
                if turn.get("role") == "user" and str(turn.get("content", "")).strip()
            ),
            None,
        )
        if not previous or previous == query.strip():
            return context

        combined = f"{previous}\n{query}"
        try:
            ranked = self.retriever.rank_heritage_names(combined)
            resolved = self.query_processor.process(combined, ranked)
        except (RagError, LlmError) as exc:
            _log.info("Không phân giải được câu nối tiếp bằng lịch sử: %s", exc)
            return context
        if resolved.needs_clarification or not resolved.heritage_name:
            return context
        # Giữ nguyên câu hỏi gốc cho lời kể; chỉ mượn di sản/intent vừa phân giải.
        return QueryContext(
            original_query=query.strip(),
            normalized_query=context.normalized_query,
            intent=resolved.intent,
            requested_length=resolved.requested_length,
            heritage_name=resolved.heritage_name,
            needs_clarification=False,
            clarification_question="",
        )

    def list_heritages(self) -> str:
        lines = ["Các di sản hiện có trong kho tri thức:"]
        lines.extend(
            f"{index}. {item['name']}"
            for index, item in enumerate(self.repository.all(), start=1)
        )
        return "\n".join(lines)
