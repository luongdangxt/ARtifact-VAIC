from __future__ import annotations

from pathlib import Path
import re
import time

from .config import Settings
from .embeddings import strip_vietnamese_accents
from .fpt_speech import FPTSpeechToText, FPTTextToSpeech
from .guardrails import HeritageGuardrails
from .ingest import ingest_documents, iter_source_files
from .llm import NarratorLLM
from .models import PipelineResponse
from .retriever import HeritageRetriever
from .semantic_router import SemanticRouter
from .vector_store import ChromaVectorStore


def _build_persona(
    name: str | None, craft: str | None, bio: str | None
) -> dict[str, str] | None:
    """Gom thông tin nhập vai nghệ nhân; None nếu không có gì -> dùng persona chung."""
    fields = {
        key: value.strip()
        for key, value in (("name", name), ("craft", craft), ("bio", bio))
        if value and value.strip()
    }
    return fields or None


def _contextualize_question(
    question: str,
    history: list[dict[str, str]] | None,
    persona: dict[str, str] | None = None,
) -> str:
    """Resolve a vague follow-up from conversation and the currently scanned artisan."""
    words = re.findall(r"[\wÀ-ỹ]+", question.lower())
    follow_up_markers = {
        "nó", "no", "đó", "do", "này", "nay", "vậy", "vay", "thế", "the",
        "còn", "con", "kia", "cái", "cai", "bức", "buc", "thêm", "them",
    }
    if len(words) > 8 and not follow_up_markers.intersection(words):
        return question

    previous_user = next(
        (
            item.get("content", "").strip()
            for item in reversed(history or [])
            if item.get("role") == "user" and item.get("content", "").strip()
        ),
        "",
    )
    context: list[str] = []
    if previous_user:
        context.append(f"câu hỏi trước: {previous_user[:1000]}")
    if persona:
        craft = persona.get("craft", "").strip()
        name = persona.get("name", "").strip()
        if craft:
            context.append(f"di sản đang được quét: {craft}")
        elif name:
            context.append(f"nhân vật đang được quét: {name}")
    if not context:
        return question
    inferred_intent = _infer_retrieval_intent(question)
    intent_line = f"\nÝ định được suy ra: {inferred_intent}" if inferred_intent else ""
    return f"{question}{intent_line}\nNgữ cảnh để hiểu câu hỏi: {'; '.join(context)}"


def _infer_retrieval_intent(question: str) -> str:
    plain = " ".join(re.findall(r"[\w]+", strip_vietnamese_accents(question.lower()), re.UNICODE))
    intent_patterns = (
        (("o dau", "dia ban", "cho nao", "vung nao"), "Hỏi địa bàn gắn với di sản."),
        (
            ("co tu bao gio", "ra doi", "xuat hien khi nao", "hinh thanh khi nao", "co lau chua"),
            "Hỏi niên đại ra đời hoặc hình thành chính xác của di sản.",
        ),
        (
            ("ai hat", "ai lam", "ai thuc hanh", "nguoi nao", "cong dong nao"),
            "Hỏi cộng đồng chủ thể hoặc người thực hành di sản.",
        ),
        (("unesco", "ghi danh", "vinh danh"), "Hỏi trạng thái UNESCO ghi danh của di sản."),
        (
            ("lam kieu gi", "lam sao", "cach lam", "thuc hanh the nao", "lam nhu nao"),
            "Hỏi cách thực hành hoặc kỹ thuật của di sản.",
        ),
        (
            (
                "la gi", "la sao", "cai nay", "ke nghe", "gioi thieu", "co gi hay",
                "noi them", "noi ngan gon", "tom tat",
            ),
            "Yêu cầu giới thiệu chung về di sản.",
        ),
    )
    for patterns, intent in intent_patterns:
        if any(pattern in plain for pattern in patterns):
            return intent
    return ""


def _speech_text(answer: str) -> str:
    """Remove visual citations so TTS does not read file names or '[S1]' aloud."""
    clean = re.sub(r"\s*\[S\d+\]", "", answer, flags=re.IGNORECASE)
    clean = re.sub(r"\s*\[[^\]]+\.pdf[^\]]*\]", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\n+Nguồn tham khảo:.*$", "", clean, flags=re.IGNORECASE | re.DOTALL)
    return clean.strip()


class SmartHeritageLibrary:
    def __init__(
        self,
        settings: Settings,
        guardrails: HeritageGuardrails,
        retriever: HeritageRetriever,
        router: SemanticRouter,
        narrator: NarratorLLM,
        stt: FPTSpeechToText,
        tts: FPTTextToSpeech,
    ) -> None:
        self.settings = settings
        self.guardrails = guardrails
        self.retriever = retriever
        self.router = router
        self.narrator = narrator
        self.stt = stt
        self.tts = tts

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SmartHeritageLibrary":
        settings = settings or Settings.from_env()
        cls._prepare_vector_store(settings)
        store = ChromaVectorStore(
            settings.vector_store_path,
            settings.vector_collection_name,
        )
        guardrails = HeritageGuardrails(settings.require_heritage_topic)
        return cls(
            settings=settings,
            guardrails=guardrails,
            retriever=HeritageRetriever(
                store,
                settings.top_k,
                settings.min_retrieval_score,
                settings.min_relevance_ratio,
            ),
            router=SemanticRouter(settings, guardrails),
            narrator=NarratorLLM(settings),
            stt=FPTSpeechToText(settings),
            tts=FPTTextToSpeech(settings),
        )

    @staticmethod
    def _prepare_vector_store(settings: Settings) -> None:
        store = ChromaVectorStore(
            settings.vector_store_path,
            settings.vector_collection_name,
        )
        if store.exists:
            return

        has_real_books = any(iter_source_files(settings.books_dir))
        if settings.auto_ingest_on_startup and has_real_books:
            ingest_documents(
                settings.books_dir,
                settings.vector_store_path,
                vector_collection_name=settings.vector_collection_name,
                chunk_size_words=settings.chunk_size_words,
                chunk_overlap_words=settings.chunk_overlap_words,
            )

    def ask_text(
        self,
        question: str,
        synthesize: bool = True,
        transcript: str | None = None,
        persona_name: str | None = None,
        persona_craft: str | None = None,
        persona_bio: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> PipelineResponse:
        timings: dict[str, int] = {}
        started = time.perf_counter()

        persona = _build_persona(persona_name, persona_craft, persona_bio)
        retrieval_question = _contextualize_question(question, history, persona)

        router_started = time.perf_counter()
        decision = self.router.route(retrieval_question)
        timings["semantic_router"] = self._elapsed_ms(router_started)
        if not decision.allowed:
            # Nghệ nhân vẫn phải LÊN TIẾNG kể cả khi từ chối/chào hỏi (câu ngoài phạm vi),
            # nếu không du khách sẽ tưởng NPC "im lặng". Tổng hợp giọng cho luôn câu từ chối.
            refusal_audio = None
            if synthesize:
                refusal_audio = self.tts.synthesize(decision.reason).audio_url
            return self._refusal_response(
                question, transcript, decision.reason, decision.category, timings, started, refusal_audio
            )

        retrieval_started = time.perf_counter()
        sources = self.retriever.retrieve(retrieval_question)
        timings["retriever"] = self._elapsed_ms(retrieval_started)
        llm_started = time.perf_counter()
        answer = self.narrator.generate(
            question,
            sources,
            persona=persona,
            history=history,
            inferred_intent=_infer_retrieval_intent(question),
        )
        timings["llm"] = self._elapsed_ms(llm_started)

        audio_url = None
        if synthesize:
            tts_started = time.perf_counter()
            audio = self.tts.synthesize(_speech_text(answer))
            audio_url = audio.audio_url
            timings["tts"] = self._elapsed_ms(tts_started)

        return PipelineResponse(
            allowed=True,
            question=question,
            answer=answer,
            transcript=transcript,
            sources=sources,
            audio_url=audio_url,
            timings_ms=self._finish_timings(timings, started),
        )

    def ask_audio(
        self,
        audio_bytes: bytes,
        content_type: str = "application/octet-stream",
        synthesize: bool = True,
        persona_name: str | None = None,
        persona_craft: str | None = None,
        persona_bio: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> PipelineResponse:
        started = time.perf_counter()
        transcript_started = time.perf_counter()
        transcript = self.stt.transcribe(audio_bytes, content_type)
        response = self.ask_text(
            transcript.text,
            synthesize=synthesize,
            transcript=transcript.text,
            persona_name=persona_name,
            persona_craft=persona_craft,
            persona_bio=persona_bio,
            history=history,
        )
        timings = dict(response.timings_ms)
        timings["stt"] = self._elapsed_ms(transcript_started)
        timings["total"] = self._elapsed_ms(started)
        return PipelineResponse(
            allowed=response.allowed,
            question=response.question,
            answer=response.answer,
            transcript=transcript.text,
            sources=response.sources,
            audio_url=response.audio_url,
            timings_ms=timings,
            refusal_reason=response.refusal_reason,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    @classmethod
    def _finish_timings(cls, timings: dict[str, int], started: float) -> dict[str, int]:
        timings = dict(timings)
        timings["total"] = cls._elapsed_ms(started)
        return timings

    @staticmethod
    def _has_confident_retrieval(sources: list) -> bool:
        return bool(sources and sources[0].score >= 0.18)

    @classmethod
    def _refusal_response(
        cls,
        question: str,
        transcript: str | None,
        reason: str,
        category: str,
        timings: dict[str, int],
        started: float,
        audio_url: str | None = None,
    ) -> PipelineResponse:
        return PipelineResponse(
            allowed=False,
            question=question,
            answer=reason,
            transcript=transcript,
            sources=[],
            audio_url=audio_url,
            timings_ms=cls._finish_timings(timings, started),
            refusal_reason=category,
        )
