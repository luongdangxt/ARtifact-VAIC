"""Lớp giao tiếp với Gemini API (LLM chính; dự phòng xem heritage_ai/fpt_client.py)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from heritage_ai.llm_contract import (
    ALLOWED_INTENTS,
    ALLOWED_LENGTHS,
    ANALYSIS_SCHEMA,
    LlmConfigurationError,
    LlmError,
    LlmResponseError,
    NARRATOR_SYSTEM_INSTRUCTION,
    ROUTER_SYSTEM_INSTRUCTION,
    QueryAnalysis,
    analysis_prompt,
    report_prompt,
    validate_analysis,
)
from heritage_ai.models import Evidence

# Các module cũ (local_router, tests) vẫn import QueryAnalysis/ALLOWED_* từ đây.
__all__ = [
    "ALLOWED_INTENTS",
    "ALLOWED_LENGTHS",
    "GeminiClient",
    "GeminiConfigurationError",
    "GeminiError",
    "GeminiResponseError",
    "QueryAnalysis",
]


class GeminiError(LlmError):
    """Lỗi cơ sở cho các vấn đề khi gọi Gemini."""


class GeminiConfigurationError(GeminiError, LlmConfigurationError):
    """Cấu hình Gemini bị thiếu hoặc không hợp lệ."""


class GeminiResponseError(GeminiError, LlmResponseError):
    """Gemini trả về dữ liệu không sử dụng được."""


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
        try:
            response = self._generate_content(
                contents=analysis_prompt(query, heritage_names),
                config={
                    "system_instruction": ROUTER_SYSTEM_INSTRUCTION,
                    "response_mime_type": "application/json",
                    "response_json_schema": ANALYSIS_SCHEMA,
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
        return validate_analysis(data, heritage_names)

    def generate_report(
        self,
        query: str,
        heritage_name: str,
        evidence: list[Evidence],
        requested_length: str,
    ) -> str:
        try:
            response = self._generate_content(
                contents=report_prompt(
                    query, heritage_name, evidence, requested_length
                ),
                config={
                    "system_instruction": NARRATOR_SYSTEM_INSTRUCTION,
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
