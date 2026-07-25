"""Các kiểu dữ liệu dùng chung giữa những agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueryContext:
    original_query: str
    normalized_query: str
    intent: str
    requested_length: str = "normal"
    heritage_name: str | None = None
    needs_clarification: bool = False
    clarification_question: str = ""


@dataclass(frozen=True)
class Evidence:
    title: str
    content: str
    source: str
    page: int | None = None
    score: float | None = None
    source_url: str = ""
    document_name: str = ""
    chunk_id: str = ""


@dataclass
class ResearchResult:
    heritage: dict[str, Any]
    intent: str
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified: bool = False
