import unittest
from unittest.mock import patch

from heritage_ai.gemini_client import (
    GeminiClient,
    GeminiResponseError,
    QueryAnalysis,
)
from heritage_ai.models import Evidence, QueryContext, ResearchResult
from heritage_ai.orchestrator import HeritageChatbot
from heritage_ai.report_agent import TextReportAgent
from heritage_ai.repository import HeritageRepository


class FakeGeminiClient:
    def analyze_query(self, query: str, heritage_names: list[str]) -> QueryAnalysis:
        if "Quan họ" in query:
            return QueryAnalysis("history", "normal", heritage_names[1], False, "")
        if "Nhã nhạc" in query:
            return QueryAnalysis("overview", "short", heritage_names[0], False, "")
        if "Bài Chòi" in query:
            return QueryAnalysis("overview", "normal", heritage_names[2], False, "")
        return QueryAnalysis(
            "overview", "normal", None, True, "Bạn muốn tìm hiểu di sản nào?"
        )

    def generate_report(
        self, query, heritage_name, evidence, requested_length
    ) -> str:
        return f"Lời kể Gemini về {heritage_name}: " + " ".join(
            item.content for item in evidence
        )


class CitingGeminiClient(FakeGeminiClient):
    def generate_report(
        self, query, heritage_name, evidence, requested_length
    ) -> str:
        return "Nội dung được sử dụng từ tư liệu thứ nhất [1]."


class FakeRetriever:
    FIELD_BY_INTENT = {
        "overview": "overview",
        "history": "history",
        "practice": "practice",
        "meaning": "meaning",
        "etiquette": "etiquette",
        "location": "location",
    }

    def __init__(self, repository: HeritageRepository) -> None:
        self.repository = repository

    def candidate_heritage_names(self, query: str, limit: int = 8):
        return [item["name"] for item in self.repository.all()[:limit]]

    def retrieve(self, query: str, heritage_id: str, intent: str):
        heritage = next(
            item for item in self.repository.all() if item["id"] == heritage_id
        )
        field = self.FIELD_BY_INTENT[intent]
        return [
            Evidence(
                title=field,
                content=heritage[field],
                source=heritage["sources"][0],
                page=1,
                score=0.9,
            )
        ]


class FakeResponse:
    def __init__(self, parsed=None, text=None) -> None:
        self.parsed = parsed
        self.text = text


class FakeFinishReason:
    name = "MAX_TOKENS"


class FakeCandidate:
    finish_reason = FakeFinishReason()


class TransientGeminiError(RuntimeError):
    code = 503


class RetryModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise TransientGeminiError("503 UNAVAILABLE")
        return FakeResponse(text="Thành công")


class RetryClient:
    def __init__(self) -> None:
        self.models = RetryModels()


class HeritageChatbotTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = HeritageRepository()
        self.chatbot = HeritageChatbot(
            repository=repository,
            gemini=FakeGeminiClient(),
            retriever=FakeRetriever(repository),
        )

    def test_repository_finds_name_without_diacritics(self) -> None:
        repository = HeritageRepository()
        item = repository.find("Ke cho toi ve bai choi")
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "nghe-thuat-bai-choi-trung-bo")

    def test_detects_history_intent(self) -> None:
        answer = self.chatbot.ask("Nguồn gốc của Quan họ là gì?")
        self.assertIn("được nuôi dưỡng qua nhiều thế hệ", answer)
        self.assertNotIn("Người hát thực hiện các làn điệu", answer)

    def test_unknown_heritage_returns_guidance(self) -> None:
        answer = self.chatbot.ask("Hãy kể về một di sản khác")
        self.assertIn("Bạn muốn tìm hiểu di sản nào?", answer)

    def test_short_answer(self) -> None:
        answer = self.chatbot.ask("Tóm tắt ngắn gọn về Nhã nhạc")
        self.assertIn("Nhã nhạc cung đình Huế", answer)
        self.assertNotIn("Nguồn gốc và lịch sử:", answer)

    def test_gemini_analysis_validation_rejects_unknown_heritage(self) -> None:
        analysis = GeminiClient._validate_analysis(
            {
                "intent": "overview",
                "requested_length": "normal",
                "heritage_name": "Di sản không tồn tại",
                "needs_clarification": False,
                "clarification_question": "",
            },
            ["Dân ca Quan họ Bắc Ninh"],
        )
        self.assertIsNone(analysis.heritage_name)
        self.assertTrue(analysis.needs_clarification)

    def test_gemini_client_loads_key_from_dotenv(self) -> None:
        with patch("heritage_ai.gemini_client.load_dotenv") as load_dotenv_mock:
            with patch.dict(
                "heritage_ai.gemini_client.os.environ",
                {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"},
                clear=True,
            ):
                client = GeminiClient()

        load_dotenv_mock.assert_called_once()
        self.assertEqual(client.api_key, "test-key")
        self.assertEqual(client.model, "test-model")

    def test_reports_truncated_gemini_response(self) -> None:
        response = FakeResponse(text='{"intent":')
        response.candidates = [FakeCandidate()]
        response.usage_metadata = None

        with self.assertRaisesRegex(GeminiResponseError, "giới hạn token"):
            GeminiClient._raise_if_truncated(response, "phân tích câu hỏi")

    def test_retries_transient_gemini_error(self) -> None:
        api_client = RetryClient()
        client = GeminiClient(api_key="test-key", client=api_client)
        client.max_retries = 2

        with patch("heritage_ai.gemini_client.time.sleep") as sleep_mock:
            response = client._generate_content("Câu hỏi", {})

        self.assertEqual(response.text, "Thành công")
        self.assertEqual(api_client.models.calls, 2)
        sleep_mock.assert_called_once_with(2)

    def test_report_omits_sources_and_citation_marks(self) -> None:
        context = QueryContext("Câu hỏi", "cau hoi", "overview")
        result = ResearchResult(
            heritage={"name": "Bài Chòi", "sources": [], "follow_up_questions": []},
            intent="overview",
            evidence=[
                Evidence("Mục 1", "A", "Nguồn được dùng"),
                Evidence("Mục 2", "B", "Nguồn không được dùng"),
            ],
        )

        answer = TextReportAgent(CitingGeminiClient()).compose(context, result)

        # Chỉ còn lời kể: bỏ mục nguồn tham khảo, lời rào đón và mã trích dẫn [n].
        self.assertEqual(answer, "Nội dung được sử dụng từ tư liệu thứ nhất.")
        self.assertNotIn("Nguồn tham khảo", answer)
        self.assertNotIn("Nguồn được dùng", answer)
        self.assertNotIn("Lưu ý", answer)


if __name__ == "__main__":
    unittest.main()
