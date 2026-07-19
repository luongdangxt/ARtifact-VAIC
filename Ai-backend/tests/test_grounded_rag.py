from __future__ import annotations

import unittest

from app.llm import (
    NarratorLLM,
    _answer_relevance_issues,
    _narrative_context,
    _needs_origin_evidence,
    _needs_how_to_evidence,
    _needs_practitioner_evidence,
    _normalize_heritage_terms,
    _parse_verification,
    _unsupported_claim_phrases,
    _unsupported_numbers,
)
from app.config import Settings
from app.models import SourceSnippet
from app.pipeline import _contextualize_question, _infer_retrieval_intent, _speech_text
from app.qa_pairs import is_narrative_request
from app.retriever import HeritageRetriever, _qa_matches_inferred_intent, _record_matches_focus
from app.vector_store import VectorRecord


class _FakeVectorStore:
    def __init__(self, records: list[VectorRecord]) -> None:
        self.records = records

    def load(self) -> list[VectorRecord]:
        return self.records

    def similarity_search(self, _query: str, _top_k: int) -> list[tuple[VectorRecord, float]]:
        return [(self.records[0], 0.95), (self.records[1], 0.75)]


class GroundedRetrievalTests(unittest.TestCase):
    def test_exact_qa_also_returns_intro_context_from_same_source(self) -> None:
        qa = VectorRecord(
            id="qa",
            text="Câu hỏi: Di sản được xếp vào loại hình nào?\nĐáp án: Nghệ thuật trình diễn dân gian",
            metadata={
                "source": "quan-ho.pdf",
                "title": "Dân ca Quan họ Bắc Ninh",
                "page": 1,
                "chunk_index": 4,
                "content_type": "qa_pair",
            },
            embedding=[],
        )
        intro = VectorRecord(
            id="intro",
            text=(
                "Dân ca Quan họ Bắc Ninh là di sản văn hóa phi vật thể. "
                "Hồ sơ được xếp vào loại hình Nghệ thuật trình diễn dân gian."
            ),
            metadata={
                "source": "quan-ho.pdf",
                "title": "Dân ca Quan họ Bắc Ninh",
                "page": 1,
                "chunk_index": 1,
            },
            embedding=[],
        )
        retriever = HeritageRetriever(_FakeVectorStore([qa, intro]), top_k=5, min_score=0.04, min_ratio=0.7)

        snippets = retriever.retrieve("Dân ca Quan họ Bắc Ninh được xếp vào loại hình nào?")

        self.assertEqual([item.content_type for item in snippets], ["qa_pair", "document"])
        self.assertEqual(snippets[1].chunk_id, "intro")

    def test_narrative_request_uses_document_context_not_quiz_chunk(self) -> None:
        qa = VectorRecord(
            id="qa",
            text="Câu hỏi: Di sản thuộc loại hình nào? Đáp án: Nghệ thuật trình diễn dân gian",
            metadata={
                "source": "quan-ho.pdf",
                "title": "Dân ca Quan họ Bắc Ninh",
                "page": 1,
                "chunk_index": 2,
                "content_type": "qa_pair",
            },
            embedding=[],
        )
        intro = VectorRecord(
            id="intro",
            text="Dân ca Quan họ Bắc Ninh được xếp vào loại hình Nghệ thuật trình diễn dân gian.",
            metadata={
                "source": "quan-ho.pdf",
                "title": "Dân ca Quan họ Bắc Ninh",
                "page": 1,
                "chunk_index": 1,
            },
            embedding=[],
        )
        retriever = HeritageRetriever(_FakeVectorStore([qa, intro]), top_k=5, min_score=0.04, min_ratio=0.7)

        snippets = retriever.retrieve("Hãy kể cho mình nghe về Dân ca Quan họ Bắc Ninh.")

        self.assertTrue(snippets)
        self.assertTrue(all(item.content_type == "document" for item in snippets))

    def test_prompt_treats_qa_as_evidence_not_copy_template(self) -> None:
        snippets = [
            SourceSnippet(
                chunk_id="qa",
                text="Câu hỏi: Loại hình nào? Đáp án: Nghệ thuật trình diễn dân gian",
                score=5.0,
                source="source.pdf",
                title="Quan họ",
                page=1,
                content_type="qa_pair",
            )
        ]
        prompt = NarratorLLM._build_prompt("Quan họ thuộc loại hình nào?", snippets)
        self.assertIn("DỮ KIỆN HỎI-ĐÁP", prompt)
        self.assertIn("không phải mẫu câu bắt buộc phải sao chép", prompt)

    def test_safe_fallback_summarizes_facts_without_row_number(self) -> None:
        snippet = SourceSnippet(
            chunk_id="intro",
            text=(
                "Giới thiệu chung Dân ca Quan họ Bắc Ninh là dòng số 3 trong bản chép 486 dòng. "
                "Hồ sơ được xếp vào loại hình Nghệ thuật trình diễn dân gian; "
                "địa bàn ghi nhận: Tỉnh Bắc Giang Tỉnh Bắc Ninh. "
                "Di sản này đã được UNESCO ghi danh. Hồ sơ ghi nhận cộng đồng đang thực hành, lưu truyền di sản."
            ),
            score=1.0,
            source="quan-ho.pdf",
            title="Dân ca Quan họ Bắc Ninh",
            page=1,
        )

        answer = NarratorLLM(Settings())._generate_grounded_overview([snippet])

        self.assertIn("Nghệ thuật trình diễn dân gian", answer)
        self.assertIn("UNESCO ghi danh", answer)
        self.assertNotIn("486", answer)
        self.assertNotIn("dòng nhạc", answer)

    def test_narrative_context_removes_database_bookkeeping(self) -> None:
        text = (
            "Giới thiệu chung Quan họ là dòng số 3 trong bản chép 486 dòng. "
            "Hồ sơ được xếp vào loại hình Nghệ thuật trình diễn dân gian. "
            "Di sản đã được UNESCO ghi danh. Câu hỏi – trả lời kiểm tra Câu 1. Tên là gì?"
        )
        context = _narrative_context(text)
        self.assertNotIn("486", context)
        self.assertNotIn("Câu 1", context)
        self.assertIn("Nghệ thuật trình diễn dân gian", context)

    def test_inferred_overview_intent_also_sanitizes_bookkeeping(self) -> None:
        snippet = SourceSnippet(
            chunk_id="intro",
            text=(
                "Giới thiệu chung Tranh Đông Hồ là dòng số 32 trong bản chép 486 dòng. "
                "Hồ sơ được xếp vào loại hình Nghề thủ công truyền thống."
            ),
            score=1.0,
            source="dong-ho.pdf",
            title="Tranh Đông Hồ",
            page=1,
        )
        prompt = NarratorLLM._build_prompt(
            "nói ngắn gọn thôi",
            [snippet],
            inferred_intent="Yêu cầu giới thiệu chung về di sản.",
        )
        self.assertNotIn("486", prompt)
        self.assertIn("Nghề thủ công truyền thống", prompt)


class GroundingGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = [
            SourceSnippet(
                chunk_id="source",
                text="Quyết định ghi danh ban hành ngày 27/12/2012.",
                score=1.0,
                source="003_source.pdf",
                title="Hồ sơ 003",
                page=1,
            )
        ]

    def test_rejects_number_not_present_in_sources(self) -> None:
        self.assertEqual(_unsupported_numbers("Di sản được ghi danh năm 2024. [S1]", self.sources), ["2024"])

    def test_allows_supported_numbers_and_ignores_citation_ids(self) -> None:
        self.assertEqual(_unsupported_numbers("Di sản được ghi danh năm 2012. [S1]", self.sources), [])

    def test_rejects_semantic_distortion_not_present_in_source(self) -> None:
        answer = "Đây là dòng nhạc thứ 3 và mang đậm bản sắc của vùng đất này."
        self.assertEqual(
            _unsupported_claim_phrases(answer, self.sources),
            ["dong nhac", "dam ban sac"],
        )

    def test_parses_strict_verifier_json(self) -> None:
        self.assertEqual(
            _parse_verification('{"supported":false,"unsupported_claims":["Sai địa danh"]}'),
            (False, ["Sai địa danh"]),
        )

    def test_follow_up_question_uses_previous_user_topic(self) -> None:
        query = _contextualize_question(
            "Thế nó diễn ra khi nào?",
            [{"role": "user", "content": "Hãy kể về Hội Gióng."}],
        )
        self.assertIn("Hội Gióng", query)

    def test_vague_question_uses_current_ar_artisan_topic(self) -> None:
        query = _contextualize_question(
            "Cái này là gì vậy?",
            [],
            {"name": "Liền anh Quan họ", "craft": "Dân ca Quan họ Bắc Ninh"},
        )
        self.assertIn("Dân ca Quan họ Bắc Ninh", query)

    def test_colloquial_narrative_requests_are_detected_without_accents(self) -> None:
        for question in ("ke nghe coi", "noi them di", "cai nay la sao", "co gi hay"):
            with self.subTest(question=question):
                self.assertTrue(is_narrative_request(question))

    def test_explicit_inferred_location_intent_is_not_overridden_by_old_narrative_history(self) -> None:
        resolved = (
            "ở đâu á\nÝ định được suy ra: Hỏi địa bàn gắn với di sản.\n"
            "Ngữ cảnh để hiểu câu hỏi: câu hỏi trước: Kể về Quan họ đi"
        )
        self.assertFalse(is_narrative_request(resolved))

    def test_origin_question_is_recognized_from_colloquial_wording(self) -> None:
        self.assertTrue(_needs_origin_evidence("Cái này có từ bao giờ vậy?"))

    def test_colloquial_intents_are_canonicalized_for_retrieval(self) -> None:
        expected = {
            "ở đâu á": "địa bàn",
            "ai hát vậy": "cộng đồng chủ thể",
            "có từ bao giờ": "niên đại ra đời",
            "tranh nay lam kieu gi": "kỹ thuật",
            "còn unesco thì sao": "UNESCO ghi danh",
        }
        for question, phrase in expected.items():
            with self.subTest(question=question):
                self.assertIn(phrase, _infer_retrieval_intent(question))

    def test_intent_specific_qa_filter_rejects_unrelated_name_answer(self) -> None:
        query = "Ý định được suy ra: Hỏi cách thực hành hoặc kỹ thuật của di sản."
        self.assertFalse(
            _qa_matches_inferred_intent(
                query,
                "Câu hỏi: Di sản trong hồ sơ này có tên là gì? Đáp án: Tranh dân gian Đông Hồ",
            )
        )
        self.assertTrue(
            _qa_matches_inferred_intent(
                query,
                "Câu hỏi: Kỹ thuật và nguyên liệu được sử dụng là gì? Đáp án: ...",
            )
        )

    def test_ar_focus_rejects_a_different_heritage_with_similar_intent_words(self) -> None:
        query = (
            "tranh nay lam kieu gi\nÝ định được suy ra: Hỏi cách thực hành hoặc kỹ thuật của di sản.\n"
            "Ngữ cảnh để hiểu câu hỏi: di sản đang được quét: Tranh dân gian Đông Hồ"
        )
        dong_ho = VectorRecord(
            id="dong-ho",
            text="Tranh dân gian Đông Hồ",
            metadata={"title": "Tranh dân gian Đông Hồ", "source": "dong-ho.pdf"},
            embedding=[],
        )
        la_buong = VectorRecord(
            id="la-buong",
            text="Câu hỏi: Kỹ thuật này dùng công cụ gì? Đáp án: Dùng công cụ của nghề viết lá Buông",
            metadata={"title": "Kỹ thuật viết chữ trên lá Buông", "source": "la-buong.pdf"},
            embedding=[],
        )
        self.assertTrue(_record_matches_focus(query, dong_ho))
        self.assertFalse(_record_matches_focus(query, la_buong))

        retriever = HeritageRetriever(_FakeVectorStore([dong_ho, la_buong]))
        self.assertEqual(retriever._merge_qa_results(query, [], [la_buong]), [])

    def test_practitioner_and_how_to_intents_are_detected(self) -> None:
        self.assertTrue(_needs_practitioner_evidence("ai hát vậy"))
        self.assertTrue(_needs_how_to_evidence("tranh nay lam kieu gi"))

    def test_grounded_but_irrelevant_policy_answer_is_rejected(self) -> None:
        issues = _answer_relevance_issues(
            "ke nghe coi",
            "Tư liệu không đề cập ai được phép hoặc không được phép thực hành.",
            "Yêu cầu giới thiệu chung về di sản.",
        )
        self.assertTrue(issues)

    def test_tts_does_not_read_visual_source_citations(self) -> None:
        answer = "Quan họ là nghệ thuật trình diễn dân gian. [S1]\n\nNguồn tham khảo: source.pdf."
        self.assertEqual(_speech_text(answer), "Quan họ là nghệ thuật trình diễn dân gian.")

    def test_uses_precise_unesco_terminology(self) -> None:
        self.assertEqual(
            _normalize_heritage_terms("Di sản được UNESCO công nhận năm 2012."),
            "Di sản được UNESCO ghi danh năm 2012.",
        )


if __name__ == "__main__":
    unittest.main()
