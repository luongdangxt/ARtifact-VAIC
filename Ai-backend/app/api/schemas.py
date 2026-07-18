from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    synthesize: bool = False
    transcript: str | None = None
    # Nhập vai nghệ nhân (tùy chọn). Thiếu -> giữ nguyên persona "Nghệ Nhân AI" chung.
    persona_name: str | None = Field(default=None, max_length=200)
    persona_craft: str | None = Field(default=None, max_length=200)
    persona_bio: str | None = Field(default=None, max_length=2000)


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    synthesize: bool = False


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str = Field(min_length=1, max_length=12000)
    response_format: str = "wav"
    voice: str | None = None


def public_pipeline_response(response, audio_url: str | None = None) -> dict[str, Any]:
    data = response.to_public()
    data["audio_url"] = audio_url
    return data
