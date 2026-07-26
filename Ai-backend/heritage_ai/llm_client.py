"""Chọn nhà cung cấp LLM và tự chuyển sang dự phòng khi nhà chính hỏng.

LLM_PROVIDER: auto (Gemini trước, hỏng thì FPT) | gemini | fpt.
Chỉ chuyển khi có FPT_API_KEY; không có key thì lỗi Gemini vẫn nổi lên như cũ.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, TypeVar

from heritage_ai.fpt_client import FptLlmClient
from heritage_ai.gemini_client import GeminiClient
from heritage_ai.llm_contract import LlmError, QueryAnalysis
from heritage_ai.models import Evidence

_log = logging.getLogger(__name__)

DEFAULT_PROVIDER = "auto"

T = TypeVar("T")


class LlmClient:
    """Giao diện giống GeminiClient, thêm một lớp dự phòng phía sau."""

    def __init__(
        self,
        primary: Any | None = None,
        backup: Any | None = None,
        provider: str | None = None,
    ) -> None:
        self.provider = (
            provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
        ).strip().lower()
        self.backup = backup if backup is not None else FptLlmClient()
        if self.provider == "fpt":
            self.primary = self.backup
            self.backup = None
        else:
            self.primary = primary if primary is not None else GeminiClient()
            if self.provider == "gemini":
                self.backup = None

    def _with_fallback(self, stage: str, call: Callable[[Any], T]) -> T:
        try:
            return call(self.primary)
        except LlmError as exc:
            if self.backup is None or not getattr(self.backup, "available", True):
                raise
            _log.warning("LLM chính lỗi khi %s, chuyển sang dự phòng: %s", stage, exc)
            return call(self.backup)

    def analyze_query(self, query: str, heritage_names: list[str]) -> QueryAnalysis:
        return self._with_fallback(
            "phân tích câu hỏi",
            lambda client: client.analyze_query(query, heritage_names),
        )

    def generate_report(
        self,
        query: str,
        heritage_name: str,
        evidence: list[Evidence],
        requested_length: str,
        history: list[dict] | None = None,
    ) -> str:
        return self._with_fallback(
            "tạo lời kể",
            lambda client: client.generate_report(
                query=query,
                heritage_name=heritage_name,
                evidence=evidence,
                requested_length=requested_length,
                history=history,
            ),
        )
