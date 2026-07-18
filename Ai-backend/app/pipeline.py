from __future__ import annotations

from pathlib import Path
import time

from .config import Settings
from .fpt_speech import FPTSpeechToText, FPTTextToSpeech
from .guardrails import HeritageGuardrails
from .ingest import ingest_documents, iter_source_files
from .llm import NarratorLLM
from .models import PipelineResponse
from .retriever import HeritageRetriever
from .semantic_router import SemanticRouter
from .vector_store import ChromaVectorStore


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

    def ask_text(self, question: str, synthesize: bool = True, transcript: str | None = None) -> PipelineResponse:
        timings: dict[str, int] = {}
        started = time.perf_counter()

        router_started = time.perf_counter()
        decision = self.router.route(question)
        timings["semantic_router"] = self._elapsed_ms(router_started)
        if not decision.allowed:
            return self._refusal_response(question, transcript, decision.reason, decision.category, timings, started)

        retrieval_started = time.perf_counter()
        sources = self.retriever.retrieve(question)
        timings["retriever"] = self._elapsed_ms(retrieval_started)
        llm_started = time.perf_counter()
        answer = self.narrator.generate(question, sources)
        timings["llm"] = self._elapsed_ms(llm_started)

        audio_url = None
        if synthesize:
            tts_started = time.perf_counter()
            audio = self.tts.synthesize(answer)
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
    ) -> PipelineResponse:
        started = time.perf_counter()
        transcript_started = time.perf_counter()
        transcript = self.stt.transcribe(audio_bytes, content_type)
        response = self.ask_text(transcript.text, synthesize=synthesize, transcript=transcript.text)
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
    ) -> PipelineResponse:
        return PipelineResponse(
            allowed=False,
            question=question,
            answer=reason,
            transcript=transcript,
            sources=[],
            audio_url=None,
            timings_ms=cls._finish_timings(timings, started),
            refusal_reason=category,
        )
