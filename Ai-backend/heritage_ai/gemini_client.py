"""Lớp giao tiếp duy nhất với Gemini API."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from heritage_ai.models import Evidence


ALLOWED_INTENTS = {
    "overview",
    "history",
    "practice",
    "meaning",
    "etiquette",
    "location",
}
ALLOWED_LENGTHS = {"short", "normal"}


class GeminiError(RuntimeError):
    """Lỗi cơ sở cho các vấn đề khi gọi Gemini."""


class GeminiConfigurationError(GeminiError):
    """Cấu hình Gemini bị thiếu hoặc không hợp lệ."""


class GeminiResponseError(GeminiError):
    """Gemini trả về dữ liệu không sử dụng được."""


@dataclass(frozen=True)
class QueryAnalysis:
    intent: str
    requested_length: str
    heritage_name: str | None
    needs_clarification: bool
    clarification_question: str


class GeminiClient:
    """Bọc Google Gen AI SDK để các module khác không phụ thuộc trực tiếp SDK."""

    DEFAULT_MODEL = "gemini-3.1-flash-lite"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        project_env = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=project_env)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.max_retries = max(0, int(os.getenv("GEMINI_MAX_RETRIES", "2")))
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise GeminiConfigurationError(
                "Chưa có GEMINI_API_KEY. Hãy tạo API key trong Google AI Studio "
                "và khai báo biến môi trường trước khi chạy."
            )

        try:
            from google import genai
        except ImportError as exc:
            raise GeminiConfigurationError(
                "Chưa cài google-genai. Hãy chạy: pip install -r requirements.txt"
            ) from exc

        self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_content(self, contents: str, config: dict[str, Any]) -> Any:
        """Gọi Gemini và retry có backoff khi dịch vụ tạm quá tải."""
        for attempt in range(self.max_retries + 1):
            try:
                return self._get_client().models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                if not self._is_transient_error(exc) or attempt >= self.max_retries:
                    raise
                delay = min(2 ** (attempt + 1), 8)
                print(
                    f"Gemini tạm quá tải; tự thử lại sau {delay} giây "
                    f"({attempt + 1}/{self.max_retries})...",
                    flush=True,
                )
                time.sleep(delay)
        raise GeminiResponseError("Gemini không trả về phản hồi.")

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        code = getattr(exc, "code", getattr(exc, "status_code", None))
        if str(code) in {"429", "500", "502", "503", "504"}:
            return True
        message = str(exc).upper()
        return any(
            marker in message
            for marker in (
                "429 RESOURCE_EXHAUSTED",
                "500 INTERNAL",
                "502 BAD_GATEWAY",
                "503 UNAVAILABLE",
                "504 DEADLINE_EXCEEDED",
            )
        )

    def analyze_query(
        self, query: str, heritage_names: list[str]
    ) -> QueryAnalysis:
        schema = {
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
        prompt = (
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

        try:
            response = self._generate_content(
                contents=prompt,
                config={
                    "system_instruction": (
                        "Bạn là Semantic Router tiếng Việt. Không trả lời câu hỏi; "
                        "chỉ phân tích ý định theo schema được cung cấp."
                    ),
                    "response_mime_type": "application/json",
                    "response_json_schema": schema,
                    # Gemini 3 dùng chung giới hạn output cho reasoning và JSON.
                    # Router đơn giản chỉ cần mức suy luận tối thiểu.
                    "thinking_config": {"thinking_level": "minimal"},
                    "max_output_tokens": 1024,
                },
            )
        except GeminiError:
            raise
        except Exception as exc:
            raise GeminiResponseError(f"Không gọi được Gemini API: {exc}") from exc

        self._raise_if_truncated(response, "phân tích câu hỏi")
        data = self._parse_json_response(response)
        return self._validate_analysis(data, heritage_names)

    def generate_report(
        self,
        query: str,
        heritage_name: str,
        evidence: list[Evidence],
        requested_length: str,
    ) -> str:
        source_material = []
        for index, item in enumerate(evidence, start=1):
            source_material.append(
                {
                    "citation": f"[{index}]",
                    "section": item.title,
                    "content": item.content,
                    "source": item.source,
                    "page": item.page,
                }
            )
        # Rút ngắn so với bản cũ (120/120-250/250-450 từ): thực tế Gemini viết bám
        # cận dưới nên ra ~195 từ, NPC không nói lê thê và sinh nhanh hơn ~0.7s.
        if requested_length == "short":
            length_instruction = "Tối đa 85 từ."
        elif len(evidence) <= 2:
            length_instruction = "Khoảng 85-175 từ, không lặp lại cùng một ý."
        else:
            length_instruction = "Khoảng 175-315 từ."
        prompt = (
            f"Câu hỏi của du khách: {query}\n"
            f"Di sản: {heritage_name}\n"
            f"Yêu cầu độ dài: {length_instruction}\n"
            "Tư liệu đã được hệ thống truy xuất:\n"
            f"{json.dumps(source_material, ensure_ascii=False, indent=2)}"
        )

        try:
            response = self._generate_content(
                contents=prompt,
                config={
                    "system_instruction": (
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
                    ),
                    "thinking_config": {"thinking_level": "low"},
                    "max_output_tokens": 4096,
                },
            )
        except GeminiError:
            raise
        except Exception as exc:
            raise GeminiResponseError(f"Không gọi được Gemini API: {exc}") from exc

        self._raise_if_truncated(response, "tạo lời kể")
        text = getattr(response, "text", None)
        if not text or not text.strip():
            raise GeminiResponseError("Gemini không trả về nội dung văn bản.")
        return text.strip()

    @staticmethod
    def _raise_if_truncated(response: Any, stage: str) -> None:
        for candidate in getattr(response, "candidates", None) or []:
            reason = getattr(candidate, "finish_reason", None)
            reason_name = getattr(reason, "name", str(reason))
            if reason_name == "MAX_TOKENS" or str(reason).endswith("MAX_TOKENS"):
                usage = getattr(response, "usage_metadata", None)
                thought_tokens = getattr(usage, "thoughts_token_count", None)
                detail = (
                    f" ({thought_tokens} token đã dùng cho suy luận)"
                    if thought_tokens is not None
                    else ""
                )
                raise GeminiResponseError(
                    f"Gemini bị giới hạn token khi {stage}{detail}."
                )

    @staticmethod
    def _parse_json_response(response: Any) -> dict[str, Any]:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed

        text = getattr(response, "text", None)
        try:
            data = json.loads(text or "")
        except (TypeError, json.JSONDecodeError) as exc:
            raise GeminiResponseError("Gemini trả về JSON không hợp lệ.") from exc
        if not isinstance(data, dict):
            raise GeminiResponseError("Kết quả phân tích phải là một JSON object.")
        return data

    @staticmethod
    def _validate_analysis(
        data: dict[str, Any], heritage_names: list[str]
    ) -> QueryAnalysis:
        intent = data.get("intent")
        requested_length = data.get("requested_length")
        if intent not in ALLOWED_INTENTS:
            raise GeminiResponseError(f"Intent không hợp lệ: {intent!r}")
        if requested_length not in ALLOWED_LENGTHS:
            raise GeminiResponseError(
                f"Độ dài yêu cầu không hợp lệ: {requested_length!r}"
            )

        heritage_name = str(data.get("heritage_name", "")).strip() or None
        if heritage_name not in heritage_names:
            heritage_name = None

        needs_clarification = bool(data.get("needs_clarification"))
        clarification_question = str(
            data.get("clarification_question", "")
        ).strip()
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
