from __future__ import annotations

import re
import unicodedata

from .embeddings import strip_vietnamese_accents
from .models import GuardrailDecision


PROMPT_ATTACK_PATTERNS = [
    r"ignore (all )?(previous|above) instructions",
    r"bỏ qua (mọi |tất cả )?(chỉ dẫn|hướng dẫn)",
    r"tiết lộ.*(system prompt|prompt hệ thống)",
    r"jailbreak",
    r"developer message",
    r"system prompt",
]

TOXIC_TERMS = {
    "địt",
    "đụ",
    "dm",
    "dmm",
    "fuck",
    "shit",
    "kill yourself",
}

HERITAGE_KEYWORDS = {
    "di sản",
    "lịch sử",
    "văn hóa",
    "truyền thống",
    "bảo tồn",
    "unesco",
    "đền",
    "đình",
    "chùa",
    "miếu",
    "lăng",
    "tháp",
    "cố đô",
    "phố cổ",
    "hội an",
    "huế",
    "mỹ sơn",
    "champa",
    "chăm",
    "vua",
    "triều",
    "nguyễn",
    "lý",
    "trần",
    "lê",
    "kiến trúc",
    "khảo cổ",
    "cổ vật",
    "bảo tàng",
    "danh thắng",
    "lễ hội",
    "nghệ thuật",
    "địa đạo",
    "hoàng thành",
}


class HeritageGuardrails:
    def __init__(self, require_heritage_topic: bool = True) -> None:
        self.require_heritage_topic = require_heritage_topic

    def check(self, question: str) -> GuardrailDecision:
        normalized = self._normalize(question)
        plain = strip_vietnamese_accents(normalized)
        if not normalized:
            return GuardrailDecision(False, "Câu hỏi đang trống. Mời bạn đặt một câu hỏi về di sản.", "empty")

        if len(normalized) > 1200:
            return GuardrailDecision(False, "Câu hỏi quá dài. Mời bạn hỏi ngắn gọn hơn.", "too_long")

        if any(term in normalized or term in plain for term in TOXIC_TERMS):
            return GuardrailDecision(
                False,
                "Mình chỉ có thể hỗ trợ khi câu hỏi được diễn đạt lịch sự và phù hợp.",
                "unsafe_language",
            )

        if any(re.search(pattern, normalized) or re.search(pattern, plain) for pattern in PROMPT_ATTACK_PATTERNS):
            return GuardrailDecision(
                False,
                "Mình không thể thực hiện yêu cầu can thiệp vào hướng dẫn hệ thống.",
                "prompt_attack",
            )

        if self.require_heritage_topic and not self._looks_like_heritage_topic(normalized):
            return GuardrailDecision(
                False,
                "Mình là thư viện di sản, nên chỉ trả lời các câu hỏi liên quan đến lịch sử, "
                "văn hóa, di tích, danh thắng hoặc tư liệu di sản.",
                "off_topic",
            )

        return GuardrailDecision(True, "Câu hỏi hợp lệ.", "allowed")

    @staticmethod
    def _normalize(text: str) -> str:
        return unicodedata.normalize("NFC", text).strip().lower()

    @staticmethod
    def _looks_like_heritage_topic(text: str) -> bool:
        plain = strip_vietnamese_accents(text)
        for keyword in HERITAGE_KEYWORDS:
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text):
                return True

            # Do not collapse the meaningful distinction between "chùa" and
            # "chưa" when matching accent-free text.
            if keyword == "chùa":
                continue

            plain_keyword = strip_vietnamese_accents(keyword)
            if re.search(rf"(?<!\w){re.escape(plain_keyword)}(?!\w)", plain):
                return True
        return False
