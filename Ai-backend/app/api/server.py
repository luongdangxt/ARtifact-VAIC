from __future__ import annotations

import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..config import Settings
from ..pipeline import SmartHeritageLibrary
from .schemas import (
    AskRequest,
    ChatCompletionRequest,
    SpeechRequest,
    public_pipeline_response,
)


settings = Settings.from_env()
pipeline = SmartHeritageLibrary.from_settings(settings)
app = FastAPI(title="Smart Heritage Library API", version="1.0.0")


def require_api_auth(authorization: Annotated[str | None, Header()] = None) -> None:
    if not settings.api_auth_token:
        return
    expected = f"Bearer {settings.api_auth_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai Bearer token.")


Auth = Annotated[None, Depends(require_api_auth)]


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Request, exc: RuntimeError):
    return JSONResponse(status_code=502, content={"error": {"message": str(exc), "type": "provider_error"}})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "smart-heritage-library",
        "llm_model": settings.llm_model,
        "stt_model": settings.fpt_stt_model,
        "tts_model": settings.fpt_tts_model,
        "vector_collection": settings.vector_collection_name,
        "vector_count": pipeline.retriever.vector_store.count(),
        "auth_enabled": bool(settings.api_auth_token),
    }


@app.post("/v1/ask")
def ask(payload: AskRequest, _: Auth) -> dict:
    response = pipeline.ask_text(
        payload.question,
        synthesize=payload.synthesize,
        transcript=payload.transcript,
        persona_name=payload.persona_name,
        persona_craft=payload.persona_craft,
        persona_bio=payload.persona_bio,
    )
    return public_pipeline_response(response, _public_audio_url(response.audio_url))


@app.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionRequest, _: Auth):
    question = next((message.content for message in reversed(payload.messages) if message.role == "user"), "")
    if not question.strip():
        raise HTTPException(status_code=422, detail="messages phải chứa một message user có content.")

    response = pipeline.ask_text(question, synthesize=payload.synthesize)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    if payload.stream:
        # LLM nội bộ hiện buffer toàn bộ response; SSE này giữ tương thích client nhưng chỉ phát một chunk cuối.
        event = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": payload.model or settings.llm_model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": response.answer}, "finish_reason": "stop"}],
        }
        return StreamingResponse(
            iter((f"data: {json.dumps(event, ensure_ascii=False)}\n\ndata: [DONE]\n\n",)),
            media_type="text/event-stream",
        )

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model or settings.llm_model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response.answer},
            "finish_reason": "stop",
        }],
        "sources": [source.to_public() for source in response.sources],
        "heritage": public_pipeline_response(response, _public_audio_url(response.audio_url)),
    }


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    _: Auth,
    file: UploadFile = File(...),
    model: str = Form(settings.fpt_stt_model),
    response_format: str = Form("json"),
    language: str | None = Form(None),
):
    audio_bytes = await file.read()
    _check_audio_size(audio_bytes)
    transcript = pipeline.stt.transcribe(
        audio_bytes,
        content_type=file.content_type or "application/octet-stream",
        filename=file.filename or "audio.wav",
        language=language,
    )
    if response_format == "text":
        return transcript.text
    return {"text": transcript.text, "model": model, "provider": transcript.provider}


@app.post("/v1/audio/ask")
async def audio_ask(
    _: Auth,
    file: UploadFile = File(...),
    synthesize: bool = Form(False),
    persona_name: str | None = Form(None),
    persona_craft: str | None = Form(None),
    persona_bio: str | None = Form(None),
):
    audio_bytes = await file.read()
    _check_audio_size(audio_bytes)
    response = pipeline.ask_audio(
        audio_bytes,
        content_type=file.content_type or "application/octet-stream",
        synthesize=synthesize,
        persona_name=persona_name,
        persona_craft=persona_craft,
        persona_bio=persona_bio,
    )
    return public_pipeline_response(response, _public_audio_url(response.audio_url))


@app.post("/v1/audio/speech")
def speech(payload: SpeechRequest, _: Auth):
    if payload.response_format.lower() != "wav":
        raise HTTPException(status_code=400, detail="Hiện API chỉ hỗ trợ response_format=wav.")
    audio = pipeline.tts.synthesize(payload.input)
    path = _audio_path(audio.audio_url)
    if path is None:
        raise HTTPException(status_code=502, detail="FPT TTS không trả về file âm thanh.")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.get("/v1/audio/files/{filename}")
def audio_file(filename: str, _: Auth):
    path = _audio_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh.")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


def _check_audio_size(audio_bytes: bytes) -> None:
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="File âm thanh rỗng.")
    if len(audio_bytes) > settings.api_max_audio_bytes:
        raise HTTPException(status_code=413, detail="File âm thanh vượt quá giới hạn cho phép.")


def _audio_path(value: str | None) -> Path | None:
    if not value:
        return None
    root = (settings.root_dir / "logs" / "tts").resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate.parent != root or candidate.suffix.lower() != ".wav" or not candidate.is_file():
        return None
    return candidate


def _public_audio_url(value: str | None) -> str | None:
    path = _audio_path(value)
    return f"/v1/audio/files/{path.name}" if path else None
