"""LLM dự phòng: gpt-oss-120b trên FPT Cloud Marketplace (API kiểu OpenAI).

Dùng khi Gemini hỏng/hết quota. Cùng prompt, cùng schema với GeminiClient
(heritage_ai/llm_contract.py) nên câu trả lời giữ nguyên giọng NPC nghệ nhân.

gpt-oss trả phần suy luận ở trường `reasoning` RIÊNG, không lẫn vào `content`,
nhưng token suy luận vẫn tính vào max_tokens — vì thế mỗi lần gọi đều đặt
reasoning_effort thấp và chừa dư max_tokens.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from heritage_ai.llm_contract import (
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

_log = logging.getLogger(__name__)


class FptLlmError(LlmError):
    """Lỗi khi gọi LLM của FPT."""


class FptLlmConfigurationError(FptLlmError, LlmConfigurationError):
    """Thiếu FPT_API_KEY hoặc cấu hình không hợp lệ."""


class FptLlmResponseError(FptLlmError, LlmResponseError):
    """FPT trả về dữ liệu không dùng được."""


class FptLlmClient:
    """Bọc endpoint /v1/chat/completions của FPT, cùng giao diện với GeminiClient."""

    DEFAULT_URL = "https://mkp-api.fptcloud.com/v1/chat/completions"
    DEFAULT_MODEL = "gpt-oss-120b"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        url: str | None = None,
    ) -> None:
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
        self.api_key = api_key or os.getenv("FPT_API_KEY", "").strip()
        self.model = model or os.getenv("FPT_LLM_MODEL", self.DEFAULT_MODEL)
        self.url = url or os.getenv("FPT_LLM_URL", self.DEFAULT_URL)
        self.max_retries = max(0, int(os.getenv("FPT_LLM_MAX_RETRIES", "1")))
        self.timeout = float(os.getenv("FPT_LLM_TIMEOUT", "90"))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise FptLlmConfigurationError(
                "Chưa có FPT_API_KEY cho LLM dự phòng."
            )
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(
                        {"model": self.model, **payload}, ensure_ascii=False
                    ).encode("utf-8"),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last = str(exc)
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise FptLlmResponseError(
                            f"FPT trả về JSON không hợp lệ: {resp.text[:160]}"
                        ) from exc
                last = f"HTTP {resp.status_code}: {resp.text[:160]}"
                if resp.status_code not in {429, 500, 502, 503, 504}:
                    break
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))
        raise FptLlmResponseError(f"FPT {self.model} lỗi: {last}")

    @staticmethod
    def _message_text(data: dict[str, Any], stage: str) -> str:
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise FptLlmResponseError(
                f"FPT không trả về nội dung khi {stage}."
            ) from exc
        content = (choice.get("message") or {}).get("content") or ""
        if choice.get("finish_reason") == "length" and not content.strip():
            # Hết token trước khi kịp viết câu trả lời (thường do suy luận dài).
            raise FptLlmResponseError(f"FPT bị giới hạn token khi {stage}.")
        if not content.strip():
            raise FptLlmResponseError(f"FPT trả về nội dung rỗng khi {stage}.")
        return content.strip()

    def analyze_query(self, query: str, heritage_names: list[str]) -> QueryAnalysis:
        payload = {
            "messages": [
                {"role": "system", "content": ROUTER_SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": analysis_prompt(query, heritage_names),
                },
            ],
            "reasoning_effort": "low",
            "max_tokens": 1024,
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_analysis",
                    "schema": ANALYSIS_SCHEMA,
                },
            },
        }
        # Guided decoding của vLLM thỉnh thoảng vẫn nhả JSON vỡ (đo được ~1/13 lần,
        # thường là dấu nháy chưa escape trong clarification_question). Sinh lại một
        # lần nữa rẻ hơn (~1.3s) và gần như luôn ra JSON hợp lệ.
        last: json.JSONDecodeError | None = None
        for _ in range(2):
            text = self._message_text(self._chat(payload), "phân tích câu hỏi")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                _log.warning("FPT trả JSON vỡ, sinh lại: %s", exc)
                last = exc
                continue
            if not isinstance(parsed, dict):
                raise FptLlmResponseError("Kết quả phân tích phải là một JSON object.")
            return validate_analysis(parsed, heritage_names)
        raise FptLlmResponseError("FPT trả về JSON không hợp lệ.") from last

    def generate_report(
        self,
        query: str,
        heritage_name: str,
        evidence: list[Evidence],
        requested_length: str,
        history: list[dict] | None = None,
    ) -> str:
        data = self._chat(
            {
                "messages": [
                    {"role": "system", "content": NARRATOR_SYSTEM_INSTRUCTION},
                    {
                        "role": "user",
                        "content": report_prompt(
                            query, heritage_name, evidence, requested_length, history
                        ),
                    },
                ],
                "reasoning_effort": "low",
                "max_tokens": 2048,
                # Cùng lý do với GeminiClient: giữ câu trả lời nhất quán.
                "temperature": 0.2,
            }
        )
        return self._message_text(data, "tạo lời kể")
