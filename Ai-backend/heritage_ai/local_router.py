"""Semantic Router chạy LOCAL, thay cho GeminiClient.analyze_query.

Router bằng Gemini đo được 2.1s/câu — chiếm gần một nửa độ trễ của cả pipeline —
trong khi việc nó làm đã có sẵn kết quả: vector search vừa xếp hạng di sản xong,
còn intent thì tiếng Việt hỏi rất lộ ("có từ bao giờ", "ở đâu", "ý nghĩa"...).
Router này quyết định trong ~0.03s (chỉ tốn 1 lần embed đã phải làm dù sao).

Nó CÓ QUYỀN từ chối trả lời: khi hai di sản đầu bảng bám sát nhau (câu hỏi mơ hồ
kiểu "kể cho tôi nghe"), route() trả None để QueryProcessor nhờ Gemini phân giải.
Đường chậm đó hiếm khi chạy, và đúng là những câu duy nhất cần tới LLM.

Vì sao intent KHÔNG dùng embedding: đã đo cosine với 6 câu mô tả intent — khoảng
cách giữa hạng nhất và hạng nhì chỉ 0.005-0.06 và sai ở những câu rõ ràng ("in
tranh như thế nào" ra location). Từ khoá đúng 12/12 trên cùng bộ câu hỏi đó.
"""

from __future__ import annotations

import os

from heritage_ai.gemini_client import QueryAnalysis
from heritage_ai.text_utils import normalize_text

# Từ khoá đã chuẩn hoá (bỏ dấu, thường hoá) -> intent. Khớp theo TỪ trọn vẹn, câu
# nào trúng nhiều từ khoá của intent nào thì thuộc về intent đó.
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "etiquette": (
        "luu y", "chu y", "ung xu", "kieng", "kieng ky", "cam ky", "quy tac",
        "nen lam gi", "khong nen", "phep tac", "trang phuc", "co duoc phep",
    ),
    "location": (
        "o dau", "dia ban", "dia diem", "tinh nao", "vung nao", "lang nao",
        "noi nao", "khong gian", "dia phuong", "nam o", "den dau", "o tinh",
    ),
    "history": (
        "tu bao gio", "bao gio", "khi nao", "nguon goc", "lich su", "ra doi",
        "hinh thanh", "bat nguon", "co tu", "tu khi nao", "nam nao", "the ky",
        "xa xua", "co xua", "phat trien qua",
    ),
    "meaning": (
        "y nghia", "gia tri", "bieu tuong", "vai tro", "tam quan trong",
        "tai sao", "vi sao", "the hien dieu gi", "noi len dieu gi",
    ),
    # Không để "cach" trơ trọi: nó là một từ hoàn chỉnh trong "cách mạng", "cách đây".
    "practice": (
        "nhu the nao", "the nao", "ra sao", "cach lam", "cach thuc", "bang cach",
        "quy trinh", "lam bang", "chat lieu", "nguyen lieu", "ky thuat",
        "truyen day", "trinh dien", "bieu dien", "thuc hanh", "cac buoc",
        "che tac", "lam ra",
    ),
    "overview": (
        "la gi", "gioi thieu", "tong quan", "khai quat", "ke ve", "noi ve",
        "tim hieu", "la mon gi",
    ),
}

# Hoà điểm thì theo thứ tự này: intent hẹp (đòi tư liệu chuyên biệt) ưu tiên hơn
# intent rộng, vì "overview" luôn là lựa chọn an toàn ở cuối.
INTENT_PRIORITY = ("etiquette", "location", "meaning", "history", "practice", "overview")

# Du khách xin bản ngắn -> report_agent rút còn tối đa 85 từ.
SHORT_KEYWORDS = (
    "ngan gon", "tom tat", "van tat", "so luoc", "noi ngan", "vai cau",
    "mot cau", "nhanh gon", "ngan thoi",
)

# Score hạng nhất phải hơn hạng nhì chừng này thì mới coi là chắc chắn. Đo trên bộ
# câu hỏi mẫu: câu rõ ràng cách nhau 0.046-0.075, câu mơ hồ/lạc đề chỉ 0.008-0.020.
DEFAULT_MARGIN = 0.03

# Câu hỏi thăm dò HỆ THỐNG (model gì, prompt, ai lập trình...) — chặn trước khi
# đụng tới RAG/LLM. Khớp theo từ trọn vẹn trên chuỗi đã bỏ dấu. Cẩn thận với từ
# ngắn: KHÔNG đưa "ai" (nghĩa tiếng Việt là "người nào") hay "bot" ("bột" bỏ dấu
# thành "bot" — tranh Đông Hồ có "bột vỏ điệp") đứng một mình vào đây. Từ có nghĩa
# di sản hợp lệ cũng phải ghép thêm ngữ cảnh AI: "hệ thống" ("hệ thống Tiểu nhạc",
# "Hệ thống Tam tòa Thánh Mẫu" là câu gợi ý chính thống), "mô hình", "máy chủ"
# ("mấy chú" bỏ dấu thành "may chu").
SYSTEM_PROBE_KEYWORDS = (
    "he thong cua ban", "he thong ai", "he thong nay", "he thong gi",
    "mo hinh ngon ngu", "mo hinh ai", "mo hinh gi", "mo hinh nao",
    "may chu cua ban", "may chu nao",
    "model", "prompt", "chatbot", "tri tue nhan tao",
    "gemini", "gpt", "openai", "llm", "api", "server", "database",
    "du lieu huan luyen", "huan luyen", "training", "ma nguon", "source code",
    "lap trinh", "thuat toan", "cong nghe", "phan mem", "ai tao ra",
    "ai lap trinh", "ai phat trien", "ai xay dung", "ai viet ra",
)


class LocalRouter:
    def __init__(self, margin: float | None = None) -> None:
        self.margin = (
            margin
            if margin is not None
            else float(os.getenv("ROUTER_MARGIN", str(DEFAULT_MARGIN)))
        )

    def route(
        self, query: str, ranked: list[tuple[str, float]]
    ) -> QueryAnalysis | None:
        """None = không đủ chắc chắn về di sản, hãy để Gemini phân giải."""
        if not ranked:
            return None

        top_name, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        # Chỉ còn đúng một ứng viên thì không có gì để nhầm.
        if len(ranked) > 1 and top_score - runner_up < self.margin:
            return None

        normalized = normalize_text(query)
        return QueryAnalysis(
            intent=classify_intent(normalized),
            requested_length=classify_length(normalized),
            heritage_name=top_name,
            needs_clarification=False,
            clarification_question="",
        )


def _matches(normalized: str, keyword: str) -> bool:
    """Khớp theo từ trọn vẹn: "ca" không dính vào "cach", "o dau" không dính "dau nam"."""
    return f" {keyword} " in f" {normalized} "


def is_system_probe(normalized: str) -> bool:
    """True nếu câu hỏi (đã normalize_text) thăm dò về hệ thống/mô hình AI."""
    return any(_matches(normalized, keyword) for keyword in SYSTEM_PROBE_KEYWORDS)


def classify_intent(normalized: str) -> str:
    """Intent từ từ khoá; không câu nào trúng thì "overview" (rộng nhất, an toàn nhất).

    "overview" là mặc định có chủ đích: vector_store.search KHÔNG lọc metadata khi
    intent là overview, nên đoán trượt cũng không làm mất tư liệu.
    """
    hits = {
        intent: sum(1 for keyword in keywords if _matches(normalized, keyword))
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    best = max(hits.values(), default=0)
    if best == 0:
        return "overview"
    return next(intent for intent in INTENT_PRIORITY if hits[intent] == best)


def classify_length(normalized: str) -> str:
    return (
        "short"
        if any(_matches(normalized, keyword) for keyword in SHORT_KEYWORDS)
        else "normal"
    )
