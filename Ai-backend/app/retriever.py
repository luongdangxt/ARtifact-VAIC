from __future__ import annotations

import re

from .embeddings import strip_vietnamese_accents
from .models import SourceSnippet
from .qa_pairs import is_narrative_request, normalized_terms, qa_record_score
from .vector_store import ChromaVectorStore


class HeritageRetriever:
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        top_k: int = 5,
        min_score: float = 0.04,
        min_ratio: float = 0.35,
    ) -> None:
        self.vector_store = vector_store
        self.top_k = top_k
        self.min_score = min_score
        self.min_ratio = min_ratio

    def retrieve(self, question: str) -> list[SourceSnippet]:
        records = self.vector_store.load()
        expanded_question = _expand_heritage_aliases(question)
        narrative_request = is_narrative_request(question)
        results = self.vector_store.similarity_search(expanded_question, max(self.top_k * 4, self.top_k))
        results.extend(self._lexical_matches(expanded_question, records))
        results = [
            (record, score)
            for record, score in results
            if _record_matches_focus(expanded_question, record)
        ]
        results = [
            (record, score)
            for record, score in results
            if record.metadata.get("content_type") != "qa_pair"
            or _qa_matches_inferred_intent(
                expanded_question,
                record.text,
                f"{record.metadata.get('title', '')} {record.metadata.get('source', '')}",
            )
        ]
        if narrative_request:
            # Với yêu cầu kể/giới thiệu, quiz hành chính là chất liệu rất tệ và dễ
            # khiến model đọc nguyên đáp án hoặc hiểu sai "dòng dữ liệu" thành
            # "dòng nhạc". Chỉ dùng các đoạn văn giới thiệu có ngữ cảnh.
            results = [
                (record, score)
                for record, score in results
                if record.metadata.get("content_type") != "qa_pair"
            ]
            results.sort(key=lambda item: item[1], reverse=True)
        else:
            results = self._merge_qa_results(expanded_question, results, records)
        results = self._prefer_exact_short_phrase(question, results)
        if not results:
            return []

        best_score = results[0][1]
        threshold = max(self.min_score, best_score * self.min_ratio)
        if best_score >= 2.0:
            threshold = max(threshold, best_score * 0.90)
        selected: list[tuple[object, float]] = []
        seen_source_types: set[tuple[str, str]] = set()
        for record, score in results:
            if score < threshold:
                continue
            metadata = record.metadata
            source_name = str(metadata.get("source", "unknown"))
            content_type = str(metadata.get("content_type", "document"))
            if content_type != "qa_pair" and (source_name, "qa_pair") in seen_source_types:
                # Chọn companion có chủ đích ở dưới (ưu tiên phần mở đầu của hồ sơ),
                # thay vì lấy chunk QA dài nhưng tình cờ có điểm lexical cao.
                continue
            source_key = (source_name, content_type)
            if source_key in seen_source_types:
                continue
            seen_source_types.add(source_key)
            selected.append((record, score))
            if len(selected) >= self.top_k:
                break

        # Một QA exact-match là bằng chứng tốt cho dữ kiện, nhưng nếu chỉ gửi đúng
        # hai dòng Câu hỏi/Đáp án thì LLM không có chất liệu để diễn đạt tự nhiên.
        # Luôn ghép thêm đoạn văn thường tốt nhất từ chính PDF đó, kể cả khi đoạn
        # này thấp hơn ngưỡng 90% dành cho QA match.
        qa_sources = {
            str(record.metadata.get("source", "unknown"))
            for record, _ in selected
            if record.metadata.get("content_type") == "qa_pair"
        }
        for source_name in qa_sources:
            if len(selected) >= self.top_k:
                break
            if (source_name, "document") in seen_source_types:
                continue
            companion_candidates = [
                (record, score)
                for record, score in results
                if str(record.metadata.get("source", "unknown")) == source_name
                and record.metadata.get("content_type") != "qa_pair"
            ]
            companion = min(
                companion_candidates,
                key=lambda item: (
                    item[0].metadata.get("page", 9999),
                    item[0].metadata.get("chunk_index", 9999),
                    -item[1],
                ),
                default=None,
            )
            if companion is not None:
                selected.append(companion)
                seen_source_types.add((source_name, "document"))

        selected.sort(key=lambda item: (item[0].metadata.get("content_type") != "qa_pair", -item[1]))
        return [self._to_snippet(record, score) for record, score in selected[: self.top_k]]

    @staticmethod
    def _to_snippet(record, score: float) -> SourceSnippet:
        metadata = record.metadata
        return SourceSnippet(
            chunk_id=record.id,
            text=record.text,
            score=score,
            source=str(metadata.get("source", "unknown")),
            title=str(metadata.get("title", metadata.get("source", "unknown"))),
            page=metadata.get("page"),
            content_type=str(metadata.get("content_type", "document")),
        )

    def _merge_qa_results(self, question: str, vector_results: list, records: list | None = None) -> list:
        qa_results = []
        for record in records if records is not None else self.vector_store.load():
            metadata = record.metadata
            if not _record_matches_focus(question, record):
                continue
            if metadata.get("content_type") == "qa_pair" and not _qa_matches_inferred_intent(
                question,
                record.text,
                f"{metadata.get('title', '')} {metadata.get('source', '')}",
            ):
                continue
            qa_score = qa_record_score(
                question,
                record.text,
                str(metadata.get("title", "")),
                str(metadata.get("source", "")),
            )
            if qa_score >= 0.85:
                # Keep QA matches above normal vector scores so embedded answers win.
                qa_bonus = 4.0 if metadata.get("content_type") == "qa_pair" else 3.0
                qa_results.append((record, qa_bonus + qa_score))

        merged = {}
        for record, score in qa_results + vector_results:
            current = merged.get(record.id)
            if current is None or score > current[1]:
                merged[record.id] = (record, score)
        return sorted(merged.values(), key=lambda item: item[1], reverse=True)

    @staticmethod
    def _lexical_matches(question: str, records: list) -> list[tuple[object, float]]:
        """Rescue named-entity matches that hashing similarity can miss."""
        query_terms = set(normalized_terms(question))
        query_terms -= {
            "la", "là", "gi", "gì", "nao", "nào", "duoc", "được", "the", "thế",
            "vao", "vào", "luc", "lúc", "khi", "năm", "nam", "ngay", "ngày",
            "theo", "ve", "về", "cua", "của", "cho", "mot", "một", "nhung", "những",
        }
        if not query_terms:
            return []

        matches: list[tuple[object, float]] = []
        for record in records:
            metadata = record.metadata
            haystack = set(
                normalized_terms(
                    " ".join(
                        [
                            str(metadata.get("title", "")),
                            str(metadata.get("source", "")),
                            record.text,
                        ]
                    )
                )
            )
            overlap = query_terms.intersection(haystack)
            if not overlap:
                continue
            title_terms = set(normalized_terms(str(metadata.get("title", ""))))
            title_overlap = len(query_terms.intersection(title_terms))
            score = 0.80 + (len(overlap) / max(1, len(query_terms))) + (0.20 * title_overlap)
            matches.append((record, score))
        return matches

    @staticmethod
    def _prefer_exact_short_phrase(question: str, results: list) -> list:
        terms = _terms(question)
        if not terms or len(terms) > 3:
            return results

        phrase = " ".join(terms)
        matches = []
        for record, score in results:
            metadata = record.metadata
            haystack = _normalized_words(
                " ".join(
                    [
                        str(metadata.get("title", "")),
                        str(metadata.get("source", "")),
                        record.text,
                    ]
                )
            )
            if phrase in haystack:
                matches.append((record, score))

        return matches or results


def _terms(text: str) -> list[str]:
    normalized = strip_vietnamese_accents(text.lower())
    return re.findall(r"[\w]+", normalized, re.UNICODE)


def _normalized_words(text: str) -> str:
    return " ".join(_terms(text))


def _expand_heritage_aliases(question: str) -> str:
    plain = " ".join(normalized_terms(question))
    additions: list[str] = []
    if any(phrase in plain for phrase in ("am nhac hoang gia", "thoi nguyen", "am nhac cung dinh")):
        additions.append("Nhã nhạc Âm nhạc Cung đình Việt Nam")
    if "vinh danh" in plain or "ghi danh" in plain:
        additions.append("UNESCO ghi danh năm")
    return f"{question} {' '.join(additions)}".strip()


def _focus_terms(question: str) -> list[str]:
    plain = " ".join(normalized_terms(question))
    match = re.search(r"di san dang duoc quet\s+(.+?)(?:\s+nhan vat|$)", plain)
    if not match:
        return []
    focus_text = re.split(
        r"\s+(?:nha nhac am nhac cung dinh|unesco ghi danh nam)\b",
        match.group(1),
        maxsplit=1,
    )[0]
    # Giữ toàn bộ tên craft thay vì chỉ "đông hồ": cụm đầy đủ phân biệt
    # Tranh dân gian Đông Hồ với "lễ cúng dòng họ" sau khi bỏ dấu.
    return normalized_terms(focus_text)


def _record_matches_focus(question: str, record) -> bool:
    focus = _focus_terms(question)
    if not focus:
        return True
    metadata = record.metadata
    haystack = " ".join(normalized_terms(f"{metadata.get('title', '')} {metadata.get('source', '')}"))
    return " ".join(focus) in haystack


def _qa_matches_inferred_intent(
    question: str,
    record_text: str,
    record_context: str = "",
) -> bool:
    question_plain = " ".join(normalized_terms(question))
    if "y dinh duoc suy ra" not in question_plain:
        return True
    focus = _focus_terms(question)
    if focus:
        context_words = " ".join(normalized_terms(record_context or record_text))
        if " ".join(focus) not in context_words:
            return False
    record_plain = " ".join(normalized_terms(record_text))
    intent_requirements = (
        ("hoi dia ban", ("dia ban", "o dau", "tinh ", "thanh pho")),
        ("hoi nien dai", ("nien dai", "ra doi", "hinh thanh", "xuat hien", "khong the tu suy ra")),
        (
            "hoi cong dong",
            ("cong dong chu the", "nguoi thuc hanh", "ai thuc hanh", "vai tro co ban"),
        ),
        ("hoi trang thai unesco", ("unesco", "ghi danh")),
        (
            "hoi cach thuc hanh",
            ("cach lam", "ky thuat", "quy trinh", "thuc hanh nhu", "nguyen lieu", "cong cu"),
        ),
    )
    for intent_marker, required_phrases in intent_requirements:
        if intent_marker in question_plain:
            return any(phrase in record_plain for phrase in required_phrases)
    return True
