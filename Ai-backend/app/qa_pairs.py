from __future__ import annotations

from dataclasses import dataclass
import re

from .embeddings import strip_vietnamese_accents
from .models import SourceSnippet


QUESTION_CUE_TERMS = {
    "ai",
    "gi",
    "gì",
    "nao",
    "nào",
    "dau",
    "đâu",
    "khi",
    "luc",
    "lúc",
    "bao",
    "nhieu",
    "nhiêu",
    "may",
    "mấy",
    "vi",
    "vì",
    "sao",
    "tai",
    "tại",
    "the",
    "thế",
    "nhu",
    "như",
    "thuoc",
    "thuộc",
    "loai",
    "loại",
    "hinh",
    "hình",
    "dia",
    "địa",
    "phuong",
    "phương",
    "quyet",
    "quyết",
    "dinh",
    "định",
    "ngay",
    "ngày",
    "thang",
    "tháng",
    "nam",
    "năm",
    "so",
    "số",
    "stt",
    "nguon",
    "nguồn",
}

GENERIC_QA_TERMS = QUESTION_CUE_TERMS.union(
    {
        "la",
        "là",
        "co",
        "có",
        "cua",
        "của",
        "ve",
        "về",
        "trong",
        "mot",
        "một",
        "cac",
        "các",
        "nhung",
        "những",
        "duoc",
        "được",
    }
)


QA_RE = re.compile(
    r"(?:Câu|Cau)\s*\d+\s*[\.:]\s*(?P<question>.*?\?)\s*"
    r"(?:Đáp án|Dap an)\s*[:：]\s*(?P<answer>.*?)(?=\s*(?:Câu|Cau)\s*\d+\s*[\.:]|\s*$)",
    re.IGNORECASE | re.DOTALL,
)

COMPACT_QA_RE = re.compile(
    r"C(?:âu|au)\s+h(?:ỏi|oi)\s*[:：:]\s*(?P<question>.*?)\s*"
    r"(?:Đáp án|Dap an)\s*[:：:]\s*(?P<answer>.*)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class QAPair:
    question: str
    answer: str


@dataclass(frozen=True)
class QAMatch:
    pair: QAPair
    snippet: SourceSnippet
    score: float


def extract_qa_pairs(text: str) -> list[QAPair]:
    pairs: list[QAPair] = []
    for match in QA_RE.finditer(text):
        question = _clean(match.group("question"))
        answer = _clean(match.group("answer"))
        if question and answer:
            pairs.append(QAPair(question=question, answer=answer))
    if not pairs:
        for match in COMPACT_QA_RE.finditer(text):
            question = _clean(match.group("question"))
            answer = _clean(match.group("answer"))
            if question and answer:
                pairs.append(QAPair(question=question, answer=answer))
    return pairs


def best_qa_match(question: str, snippets: list[SourceSnippet], min_score: float = 0.85) -> QAMatch | None:
    if not is_question_like(question):
        return None

    best: QAMatch | None = None
    question_terms = _question_terms(question)
    if not question_terms:
        return None

    for snippet in snippets:
        for pair in extract_qa_pairs(snippet.text):
            score = qa_pair_score(
                question_terms,
                pair,
                f"{snippet.title} {snippet.source}",
            )
            if score < min_score:
                continue
            if best is None or score > best.score:
                best = QAMatch(pair=pair, snippet=snippet, score=score)
    return best


def qa_record_score(question: str, record_text: str, title: str, source: str) -> float:
    if not is_question_like(question):
        return 0.0

    pairs = extract_qa_pairs(record_text)
    if not pairs:
        return 0.0

    question_terms = _question_terms(question)

    best = 0.0
    for pair in pairs:
        score = qa_pair_score(question_terms, pair, f"{title} {source}")
        if score > best:
            best = score
    return best


def qa_pair_score(question_terms: set[str], pair: QAPair, title_text: str) -> float:
    pair_terms = set(normalized_terms(pair.question))
    title_terms = set(normalized_terms(title_text))
    pair_score = token_overlap(question_terms, pair_terms)
    meaningful_question_terms = question_terms.difference(GENERIC_QA_TERMS)
    meaningful_pair_terms = pair_terms.difference(GENERIC_QA_TERMS)
    meaningful_pair_score = token_overlap(meaningful_question_terms, meaningful_pair_terms)
    entity_terms = meaningful_question_terms.difference(meaningful_pair_terms)

    # A complete exact match should outrank ordinary vector hits even when
    # the question has no extra entity beyond the QA pair itself.
    if meaningful_pair_score >= 0.70:
        title_score = len(meaningful_question_terms.intersection(title_terms)) / max(1, len(meaningful_question_terms))
        return 1.25 + meaningful_pair_score + (0.25 * title_score)

    if entity_terms:
        # An exact question match is stronger evidence than the PDF title.
        title_score = len(entity_terms.intersection(title_terms)) / max(1, len(entity_terms))
        if title_score < 0.45 or meaningful_pair_score < 0.20:
            return 0.0
        return meaningful_pair_score + title_score

    # Generic questions without an entity should not globally boost every PDF.
    if meaningful_question_terms:
        return meaningful_pair_score
    return pair_score * 0.25


def normalized_terms(text: str) -> list[str]:
    normalized = strip_vietnamese_accents(text.lower()).replace("_", " ")
    return re.findall(r"[\w]+", normalized, re.UNICODE)


def _question_terms(text: str) -> set[str]:
    plain = " ".join(normalized_terms(text))
    additions: list[str] = []
    if "vinh danh" in plain or "ghi danh" in plain:
        additions.append("UNESCO ghi danh năm")
    if "am nhac hoang gia" in plain or "thoi nguyen" in plain or "am nhac cung dinh" in plain:
        additions.append("Nhã nhạc Âm nhạc Cung đình Việt Nam")
    return set(normalized_terms(f"{text} {' '.join(additions)}"))


def is_question_like(text: str) -> bool:
    if "?" in text or "？" in text:
        return True
    terms = set(normalized_terms(text))
    return bool(terms.intersection(QUESTION_CUE_TERMS))


def token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / max(1, min(len(left), len(right)))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .;:-")
