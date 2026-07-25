"""Tạo embedding cục bộ bằng Sentence Transformers."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from heritage_ai.rag.models import TextChunk


class LocalEmbeddingError(RuntimeError):
    """Không thể tải hoặc chạy model embedding cục bộ."""


class LocalEmbedder:
    """Embedding đa ngôn ngữ chạy local, không sử dụng quota Gemini."""

    DEFAULT_MODEL = "intfloat/multilingual-e5-base"

    def __init__(
        self,
        model: str | None = None,
        device: str | None = None,
        encoder: Any | None = None,
    ) -> None:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        self.model = model or os.getenv(
            "RAG_EMBEDDING_MODEL", self.DEFAULT_MODEL
        )
        self.device = device or os.getenv("RAG_EMBEDDING_DEVICE", "auto")
        self._encoder = encoder
        # Server chạy đa luồng: khoá để nhiều request cùng lúc chỉ nạp model 1 lần
        # (mỗi lần nạp ~15s + tốn RAM riêng).
        self._encoder_lock = threading.Lock()

    def embed_documents(
        self, chunks: list[TextChunk], batch_size: int = 8
    ) -> list[list[float]]:
        texts = [
            (
                "passage: "
                f"{chunk.heritage_name}. {chunk.section}. {chunk.content}"
            )
            for chunk in chunks
        ]
        return self._encode(texts, batch_size=batch_size)

    def embed_query(self, query: str) -> list[float]:
        vectors = self._encode([f"query: {query}"], batch_size=1)
        return vectors[0]

    def _load_encoder(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        with self._encoder_lock:
            # Kiểm tra lại trong khoá: luồng chờ trước cửa có thể đã nạp xong.
            if self._encoder is not None:
                return self._encoder
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise LocalEmbeddingError(
                    "Chưa cài sentence-transformers. Hãy chạy: "
                    "python3 -m pip install -r requirements.txt"
                ) from exc

            options: dict[str, Any] = {}
            if self.device != "auto":
                options["device"] = self.device
            try:
                self._encoder = SentenceTransformer(self.model, **options)
            except Exception as exc:
                raise LocalEmbeddingError(
                    f"Không tải được model embedding local {self.model}: {exc}"
                ) from exc
            return self._encoder

    def _encode(self, texts: list[str], batch_size: int) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self._load_encoder().encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except LocalEmbeddingError:
            raise
        except Exception as exc:
            raise LocalEmbeddingError(
                f"Không tạo được embedding local bằng {self.model}: {exc}"
            ) from exc
        return vectors.tolist()
