from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _choice_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() or default


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    path = Path(value.strip())
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _tts_format_env() -> str:
    return "wav"


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    books_dir: Path = ROOT_DIR / "data" / "books"
    vector_store_path: Path = ROOT_DIR / "data" / "vector_store" / "chroma"
    vector_collection_name: str = "heritage_chunks"

    fpt_api_key: str = ""
    fpt_asr_url: str = "https://mkp-api.fptcloud.com/v1/audio/transcriptions"
    fpt_tts_url: str = "https://mkp-api.fptcloud.com/v1/audio/speech"
    fpt_stt_model: str = "FPT.AI-whisper-large-v3-turbo"
    fpt_stt_language: str = "vi"
    fpt_tts_model: str = "FPT.AI-VITs"
    fpt_tts_voice: str = "std_kimngan"
    fpt_tts_speed: str = "0"
    fpt_tts_format: str = "wav"
    fpt_tts_download_timeout: int = 90
    fpt_tts_poll_interval: float = 2.0

    tts_autoplay: bool = True
    audio_record_seconds: float = 6.0
    audio_sample_rate: int = 16000

    llm_provider: str = "fpt_cloud"
    llm_api_base: str = "https://mkp-api.fptcloud.com/v1"
    llm_api_key: str = ""
    llm_model: str = "SaoLa3.1-medium"
    llm_temperature: float = 0.25
    llm_max_tokens: int = 700
    llm_stream: bool = True

    top_k: int = 5
    min_retrieval_score: float = 0.04
    min_relevance_ratio: float = 0.70
    chunk_size_words: int = 260
    chunk_overlap_words: int = 60
    require_heritage_topic: bool = True
    auto_ingest_on_startup: bool = False

    server_host: str = "127.0.0.1"
    server_port: int = 8000
    api_auth_token: str = ""
    api_max_audio_bytes: int = 25 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(ROOT_DIR / ".env")
        return cls(
            fpt_api_key=os.getenv("FPT_API_KEY", ""),
            vector_store_path=_path_env("VECTOR_STORE_PATH", cls.vector_store_path),
            vector_collection_name=os.getenv("VECTOR_COLLECTION_NAME", cls.vector_collection_name),
            fpt_asr_url=os.getenv("FPT_ASR_URL", cls.fpt_asr_url),
            fpt_tts_url=os.getenv("FPT_TTS_URL", cls.fpt_tts_url),
            fpt_stt_model=os.getenv("FPT_STT_MODEL", cls.fpt_stt_model),
            fpt_stt_language=os.getenv("FPT_STT_LANGUAGE", cls.fpt_stt_language),
            fpt_tts_model=os.getenv("FPT_TTS_MODEL", cls.fpt_tts_model),
            fpt_tts_voice=os.getenv("FPT_TTS_VOICE", cls.fpt_tts_voice),
            fpt_tts_speed=os.getenv("FPT_TTS_SPEED", cls.fpt_tts_speed),
            fpt_tts_format=_tts_format_env(),
            fpt_tts_download_timeout=_int_env("FPT_TTS_DOWNLOAD_TIMEOUT", cls.fpt_tts_download_timeout),
            fpt_tts_poll_interval=_float_env("FPT_TTS_POLL_INTERVAL", cls.fpt_tts_poll_interval),
            tts_autoplay=_bool_env("TTS_AUTOPLAY", cls.tts_autoplay),
            audio_record_seconds=_float_env("AUDIO_RECORD_SECONDS", cls.audio_record_seconds),
            audio_sample_rate=_int_env("AUDIO_SAMPLE_RATE", cls.audio_sample_rate),
            llm_provider=_choice_env("LLM_PROVIDER", cls.llm_provider),
            llm_api_base=os.getenv("LLM_API_BASE", cls.llm_api_base),
            llm_api_key=os.getenv("LLM_API_KEY", "") or os.getenv("FPT_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", cls.llm_model),
            llm_temperature=_float_env("LLM_TEMPERATURE", cls.llm_temperature),
            llm_max_tokens=_int_env("LLM_MAX_TOKENS", cls.llm_max_tokens),
            llm_stream=_bool_env("LLM_STREAM", cls.llm_stream),
            top_k=_int_env("TOP_K", cls.top_k),
            min_retrieval_score=_float_env("MIN_RETRIEVAL_SCORE", cls.min_retrieval_score),
            min_relevance_ratio=_float_env("MIN_RELEVANCE_RATIO", cls.min_relevance_ratio),
            chunk_size_words=_int_env("CHUNK_SIZE_WORDS", cls.chunk_size_words),
            chunk_overlap_words=_int_env("CHUNK_OVERLAP_WORDS", cls.chunk_overlap_words),
            require_heritage_topic=_bool_env("REQUIRE_HERITAGE_TOPIC", cls.require_heritage_topic),
            auto_ingest_on_startup=_bool_env("AUTO_INGEST_ON_STARTUP", cls.auto_ingest_on_startup),
            server_host=os.getenv("SERVER_HOST", cls.server_host),
            server_port=_int_env("SERVER_PORT", cls.server_port),
            api_auth_token=os.getenv("API_AUTH_TOKEN", ""),
            api_max_audio_bytes=_int_env("API_MAX_AUDIO_BYTES", cls.api_max_audio_bytes),
        )
