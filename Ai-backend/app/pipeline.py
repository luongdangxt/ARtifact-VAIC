from __future__ import annotations

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


def _build_persona(name: str | None, craft: str | None, bio: str | None) -> dict[str, str] | None:
    fields = {
        key: value.strip()
        for key, value in (("name", name), ("craft", craft), ("bio", bio))
        if value and value.strip()
    }
    return fields or None


class SmartHeritageLibrary:
    def __init__(self, settings: Settings, guardrails: HeritageGuardrails, retriever: HeritageRetriever,
                 router: SemanticRouter, narrator: NarratorLLM, stt: FPTSpeechToText,
                 tts: FPTTextToSpeech) -> None:
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
        store = ChromaVectorStore(settings.vector_store_path, settings.vector_collection_name)
        guardrails = HeritageGuardrails(settings.require_heritage_topic)
        return cls(
            settings,
            guardrails,
            HeritageRetriever(store, settings.top_k, settings.min_retrieval_score, settings.min_relevance_ratio),
            SemanticRouter(settings, guardrails),
            NarratorLLM(settings),
            FPTSpeechToText(settings),
            FPTTextToSpeech(settings),
        )

    @staticmethod
    def _prepare_vector_store(settings: Settings) -> None:
        store = ChromaVectorStore(settings.vector_store_path, settings.vector_collection_name)
        if store.exists:
            return
        if settings.auto_ingest_on_startup and any(iter_source_files(settings.books_dir)):
            ingest_documents(settings.books_dir, settings.vector_store_path,
                             vector_collection_name=settings.vector_collection_name,
                             chunk_size_words=settings.chunk_size_words,
                             chunk_overlap_words=settings.chunk_overlap_words)

    def ask_text(self, question: str, synthesize: bool = True, transcript: str | None = None,
                 persona_name: str | None = None, persona_craft: str | None = None,
                 persona_bio: str | None = None) -> PipelineResponse:
        timings: dict[str, int] = {}
        started = time.perf_counter()
        persona = _build_persona(persona_name, persona_craft, persona_bio)

        router_started = time.perf_counter()
        decision = self.router.route(question)
        timings["semantic_router"] = self._elapsed_ms(router_started)
        if not decision.allowed:
            refusal_audio = self.tts.synthesize(decision.reason).audio_url if synthesize else None
            return self._refusal_response(question, transcript, decision.reason, decision.category,
                                          timings, started, refusal_audio)

        retrieval_started = time.perf_counter()
        sources = self.retriever.retrieve(question)
        timings["retriever"] = self._elapsed_ms(retrieval_started)
        llm_started = time.perf_counter()
        answer = self.narrator.generate(question, sources, persona=persona)
        timings["llm"] = self._elapsed_ms(llm_started)

        audio_url = None
        if synthesize:
            tts_started = time.perf_counter()
            audio_url = self.tts.synthesize(answer).audio_url
            timings["tts"] = self._elapsed_ms(tts_started)

        return PipelineResponse(True, question, answer, transcript, sources, audio_url,
                                self._finish_timings(timings, started))

    def ask_audio(self, audio_bytes: bytes, content_type: str = "application/octet-stream",
                  synthesize: bool = True, persona_name: str | None = None,
                  persona_craft: str | None = None, persona_bio: str | None = None) -> PipelineResponse:
        started = time.perf_counter()
        transcript_started = time.perf_counter()
        transcript = self.stt.transcribe(audio_bytes, content_type)
        response = self.ask_text(transcript.text, synthesize=synthesize, transcript=transcript.text,
                                 persona_name=persona_name, persona_craft=persona_craft, persona_bio=persona_bio)
        timings = dict(response.timings_ms)
        timings["stt"] = self._elapsed_ms(transcript_started)
        timings["total"] = self._elapsed_ms(started)
        return PipelineResponse(response.allowed, response.question, response.answer, transcript.text,
                                response.sources, response.audio_url, timings, response.refusal_reason)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    @classmethod
    def _finish_timings(cls, timings: dict[str, int], started: float) -> dict[str, int]:
        result = dict(timings)
        result["total"] = cls._elapsed_ms(started)
        return result

    @classmethod
    def _refusal_response(cls, question: str, transcript: str | None, reason: str,
                          category: str, timings: dict[str, int], started: float,
                          audio_url: str | None = None) -> PipelineResponse:
        return PipelineResponse(False, question, reason, transcript, [], audio_url,
                                cls._finish_timings(timings, started), category)
