from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SourceSnippet:
    chunk_id: str
    text: str
    score: float
    source: str
    title: str
    page: int | None = None
    content_type: str = "document"

    def to_public(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(self.score, 4)
        return data


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str
    category: str = "allowed"


@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    provider: str
    request_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class SpeechAudio:
    audio_url: str | None
    provider: str
    request_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class PipelineResponse:
    allowed: bool
    question: str
    answer: str
    transcript: str | None
    sources: list[SourceSnippet]
    audio_url: str | None
    timings_ms: dict[str, int]
    refusal_reason: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "question": self.question,
            "answer": self.answer,
            "transcript": self.transcript,
            "sources": [source.to_public() for source in self.sources],
            "audio_url": self.audio_url,
            "timings_ms": self.timings_ms,
            "refusal_reason": self.refusal_reason,
        }
