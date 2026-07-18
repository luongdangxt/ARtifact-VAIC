from __future__ import annotations

import re

from .embeddings import strip_vietnamese_accents
from .models import SourceSnippet
from .qa_pairs import normalized_terms, qa_record_score
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
        results = self.vector_store.similarity_search(expanded_question, max(self.top_k * 4, self.top_k))
        results.extend(self._lexical_matches(expanded_question, records))
        results = self._merge_qa_results(expanded_question, results, records)
        results = self._prefer_exact_short_phrase(question, results)
        if not results:
            return []

        best_score = results[0][1]
        threshold = max(self.min_score, best_score * self.min_ratio)
        if best_score >= 2.0:
            threshold = max(threshold, best_score * 0.90)
        snippets: list[SourceSnippet] = []
        seen_sources: set[str] = set()
        for record, score in results:
            if score < threshold:
                continue
            metadata = record.metadata
            source_name = str(metadata.get("source", "unknown"))
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            snippets.append(
                SourceSnippet(
                    chunk_id=record.id,
                    text=record.text,
                    score=score,
                    source=source_name,
                    title=str(metadata.get("title", metadata.get("source", "unknown"))),
                    page=metadata.get("page"),
                )
            )
            if len(snippets) >= self.top_k:
                break
        return snippets

    def _merge_qa_results(self, question: str, vector_results: list, records: list | None = None) -> list:
        qa_results = []
        for record in records if records is not None else self.vector_store.load():
            metadata = record.metadata
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
