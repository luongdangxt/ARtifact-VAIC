"""Hợp đồng chung cho mọi nhà cung cấp LLM (Gemini chính, FPT dự phòng).

Prompt, schema JSON và bước kiểm tra kết quả nằm ở đây để hai provider trả về
cùng một thứ; client chỉ còn lo phần gọi HTTP/SDK riêng của mình.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from heritage_ai.models import Evidence
from heritage_ai.text_utils import normalize_text


ALLOWED_INTENTS = {
    "overview",
    "history",
    "practice",
    "meaning",
    "etiquette",
    "location",
}
ALLOWED_LENGTHS = {"short", "normal"}


class LlmError(RuntimeError):
    """Lỗi cơ sở cho mọi vấn đề khi gọi LLM (Gemini hoặc FPT)."""


class LlmConfigurationError(LlmError):
    """Cấu hình provider bị thiếu hoặc không hợp lệ."""


class LlmResponseError(LlmError):
    """Provider trả về dữ liệu không sử dụng được."""


@dataclass(frozen=True)
class QueryAnalysis:
    intent: str
    requested_length: str
    heritage_name: str | None
    needs_clarification: bool
    clarification_question: str


ROUTER_SYSTEM_INSTRUCTION = (
    "Bạn là Semantic Router tiếng Việt. Không trả lời câu hỏi; "
    "chỉ phân tích ý định theo schema được cung cấp."
)

NARRATOR_SYSTEM_INSTRUCTION = (
    "Bạn là Nghệ nhân AI giới thiệu di sản cho du khách bằng "
    "tiếng Việt tự nhiên, gần gũi và tôn trọng cộng đồng chủ thể. "
    "Chỉ sử dụng sự kiện có trong tư liệu được cung cấp; không tự "
    "bổ sung niên đại, địa danh, danh hiệu UNESCO hoặc chi tiết "
    "nghi lễ. Trả lời trực tiếp câu hỏi, không tạo mục nguồn tham "
    "khảo, không thêm lời rào đón cuối câu. Không giả danh một nghệ "
    "nhân có thật hoặc tự nhận là thành viên cộng đồng sở hữu di "
    "sản; không dùng những cách nói như 'cha ông chúng tôi' hay "
    "'quê hương chúng tôi'. Gắn mã trích dẫn [1], [2]... ngay "
    "sau các nhận định dựa trên tư liệu tương ứng. Chỉ dùng mã "
    "trích dẫn đã có trong dữ liệu đầu vào."
)

ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": sorted(ALLOWED_INTENTS),
        },
        "requested_length": {
            "type": "string",
            "enum": sorted(ALLOWED_LENGTHS),
        },
        "heritage_name": {
            "type": "string",
            "description": (
                "Tên chính xác trong danh sách di sản; để chuỗi rỗng nếu "
                "không xác định được."
            ),
        },
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": "string"},
    },
    "required": [
        "intent",
        "requested_length",
        "heritage_name",
        "needs_clarification",
        "clarification_question",
    ],
}


def analysis_prompt(query: str, heritage_names: list[str]) -> str:
    return (
        "Phân tích câu hỏi của du khách về di sản văn hóa phi vật thể.\n"
        f"Câu hỏi: {query}\n"
        "Danh sách tên di sản được hỗ trợ:\n- "
        + "\n- ".join(heritage_names)
        + "\nChọn đúng một intent. Chỉ đặt needs_clarification=true khi "
        "không xác định được di sản hoặc yêu cầu quá mơ hồ. "
        "Danh sách trên chỉ là các ứng viên do vector search gợi ý, không "
        "đồng nghĩa ứng viên chắc chắn khớp câu hỏi. "
        "Nếu nhận diện được di sản, heritage_name phải đúng nguyên văn một "
        "tên trong danh sách. Câu hỏi ngắn vẫn có thể hợp lệ nếu là tên di sản."
    )


def length_instruction(requested_length: str, evidence_count: int) -> str:
    # Rút ngắn so với bản cũ (120/120-250/250-450 từ): thực tế LLM viết bám cận dưới
    # nên ra ~195 từ, NPC không nói lê thê và sinh nhanh hơn ~0.7s.
    if requested_length == "short":
        return "Tối đa 85 từ."
    if evidence_count <= 2:
        return "Khoảng 85-175 từ, không lặp lại cùng một ý."
    return "Khoảng 175-315 từ."


def report_prompt(
    query: str,
    heritage_name: str,
    evidence: list[Evidence],
    requested_length: str,
) -> str:
    source_material = [
        {
            "citation": f"[{index}]",
            "section": item.title,
            "content": item.content,
            "source": item.source,
            "page": item.page,
        }
        for index, item in enumerate(evidence, start=1)
    ]
    return (
        f"Câu hỏi của du khách: {query}\n"
        f"Di sản: {heritage_name}\n"
        f"Yêu cầu độ dài: {length_instruction(requested_length, len(evidence))}\n"
        "Tư liệu đã được hệ thống truy xuất:\n"
        f"{json.dumps(source_material, ensure_ascii=False, indent=2)}"
    )


def _match_heritage_name(value: str, heritage_names: list[str]) -> str | None:
    """Khớp tên di sản do LLM trả về với danh sách ứng viên.

    Ưu tiên khớp nguyên văn. Model dự phòng hay rút gọn tên ("Quan họ" thay vì
    "Dân ca Quan họ Bắc Ninh") nên chấp nhận thêm khớp theo dạng đã chuẩn hoá,
    và chỉ nhận khớp-một-phần khi có DUY NHẤT một ứng viên chứa tên đó — nhiều
    ứng viên cùng khớp nghĩa là vẫn còn mơ hồ, phải hỏi lại du khách.
    """
    if value in heritage_names:
        return value
    normalized = normalize_text(value)
    if not normalized:
        return None
    by_norm = {name: normalize_text(name) for name in heritage_names}
    exact = [name for name, norm in by_norm.items() if norm == normalized]
    if exact:
        return exact[0]
    partial = [name for name, norm in by_norm.items() if normalized in norm]
    return partial[0] if len(partial) == 1 else None


def validate_analysis(data: dict, heritage_names: list[str]) -> QueryAnalysis:
    intent = data.get("intent")
    requested_length = data.get("requested_length")
    if intent not in ALLOWED_INTENTS:
        raise LlmResponseError(f"Intent không hợp lệ: {intent!r}")
    if requested_length not in ALLOWED_LENGTHS:
        raise LlmResponseError(
            f"Độ dài yêu cầu không hợp lệ: {requested_length!r}"
        )

    raw_name = str(data.get("heritage_name", "")).strip()
    heritage_name = (
        _match_heritage_name(raw_name, heritage_names) if raw_name else None
    )

    needs_clarification = bool(data.get("needs_clarification"))
    clarification_question = str(data.get("clarification_question", "")).strip()
    if heritage_name is None:
        needs_clarification = True
    if needs_clarification and not clarification_question:
        clarification_question = "Bạn muốn tìm hiểu về di sản nào?"

    return QueryAnalysis(
        intent=intent,
        requested_length=requested_length,
        heritage_name=heritage_name,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
    )
