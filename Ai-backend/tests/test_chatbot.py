import unittest
from unittest.mock import patch

from heritage_ai.gemini_client import (
    GeminiClient,
    GeminiResponseError,
    QueryAnalysis,
)
from heritage_ai.local_router import LocalRouter, classify_intent, classify_length
from heritage_ai.models import Evidence, QueryContext, ResearchResult
from heritage_ai.orchestrator import HeritageChatbot
from heritage_ai.report_agent import TextReportAgent
from heritage_ai.repository import HeritageRepository
from heritage_ai.text_utils import normalize_text


class FakeGeminiClient:
    def __init__(self) -> None:
        self.analyze_calls = 0

    def analyze_query(self, query: str, heritage_names: list[str]) -> QueryAnalysis:
        self.analyze_calls += 1
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
    # Vị trí trong repository của di sản được nhắc tên (khớp với FakeGeminiClient).
    MENTIONS = {"Nhã nhạc": 0, "Quan họ": 1, "Bài Chòi": 2}

    def __init__(self, repository: HeritageRepository) -> None:
        self.repository = repository

    def candidate_heritage_names(self, query: str, limit: int = 8):
        return [name for name, _ in self.rank_heritage_names(query, limit)]

    def rank_heritage_names(self, query: str, limit: int = 8):
        """Giả lập vector search: di sản được nhắc tên bỏ xa phần còn lại.

        Câu không nhắc tên di sản nào -> các score sát nhau, đúng tình huống router
        local chịu thua và nhường cho Gemini phân giải.
        """
        names = [item["name"] for item in self.repository.all()[:limit]]
        ranked = [(name, 0.70 - index * 0.001) for index, name in enumerate(names)]
        mentioned = next(
            (index for text, index in self.MENTIONS.items() if text in query), None
        )
        if mentioned is not None:
            ranked[mentioned] = (names[mentioned], 0.90)
        return sorted(ranked, key=lambda item: item[1], reverse=True)

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


class LocalRouterTests(unittest.TestCase):
    def test_classifies_intent_from_vietnamese_keywords(self) -> None:
        cases = {
            "Quan họ Bắc Ninh có từ bao giờ?": "history",
            "Quan họ là gì?": "overview",
            "Tranh Đông Hồ làm bằng chất liệu gì?": "practice",
            "Người ta in tranh Đông Hồ như thế nào?": "practice",
            "Ý nghĩa của tranh Đông Hồ trong ngày Tết?": "meaning",
            "Hát quan họ ở đâu?": "location",
            "Đi xem hội Lim cần lưu ý gì?": "etiquette",
            "Nghệ nhân truyền dạy quan họ ra sao?": "practice",
            "Kể cho tôi nghe đi": "overview",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(classify_intent(normalize_text(query)), expected)

    def test_detects_short_answer_request(self) -> None:
        self.assertEqual(
            classify_length(normalize_text("Tóm tắt ngắn gọn về tranh Đông Hồ")),
            "short",
        )
        self.assertEqual(
            classify_length(normalize_text("Tranh Đông Hồ có từ bao giờ?")), "normal"
        )

    def test_generic_words_do_not_trigger_an_intent(self) -> None:
        # "cách" đứng một mình là từ thường gặp ("cách mạng", "cách đây") nên chỉ các
        # cụm cụ thể mới được tính là practice.
        self.assertEqual(classify_intent(normalize_text("Bảo tàng Cách mạng")), "overview")
        self.assertEqual(
            classify_intent(normalize_text("Tranh này làm bằng cách nào?")), "practice"
        )

    def test_gives_up_when_two_heritages_are_close(self) -> None:
        router = LocalRouter()
        self.assertIsNone(
            router.route("Kể tôi nghe", [("Quan họ", 0.78), ("Đông Hồ", 0.77)])
        )
        analysis = router.route("Quan họ có từ bao giờ?", [("Quan họ", 0.83), ("Đông Hồ", 0.76)])
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.heritage_name, "Quan họ")
        self.assertEqual(analysis.intent, "history")
        self.assertFalse(analysis.needs_clarification)

    def test_single_candidate_needs_no_margin(self) -> None:
        analysis = LocalRouter().route("Di sản này ở đâu?", [("Quan họ", 0.72)])
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.intent, "location")


class HeritageChatbotTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = HeritageRepository()
        self.gemini = FakeGeminiClient()
        self.chatbot = HeritageChatbot(
            repository=repository,
            gemini=self.gemini,
            retriever=FakeRetriever(repository),
        )

    def test_confident_question_never_calls_gemini_router(self) -> None:
        # Đây là mục tiêu của router local: bỏ hẳn một vòng gọi Gemini (~2.1s).
        self.chatbot.ask("Nguồn gốc của Quan họ là gì?")
        self.assertEqual(self.gemini.analyze_calls, 0)

    def test_ambiguous_question_falls_back_to_gemini_router(self) -> None:
        self.chatbot.ask("Hãy kể về một di sản khác")
        self.assertEqual(self.gemini.analyze_calls, 1)

    def test_local_only_mode_asks_back_instead_of_calling_gemini(self) -> None:
        self.chatbot.query_processor.mode = "local"
        answer = self.chatbot.ask("Hãy kể về một di sản khác")
        self.assertIn("Bạn muốn tìm hiểu về di sản nào?", answer)
        self.assertEqual(self.gemini.analyze_calls, 0)

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
