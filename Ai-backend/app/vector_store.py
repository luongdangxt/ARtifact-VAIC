from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .embeddings import HashingEmbedder
from .models import DocumentChunk


try:
    import chromadb
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    chromadb = None


@dataclass(frozen=True)
class VectorRecord:
    id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float]


class ChromaVectorStore:
    def __init__(
        self,
        path: Path,
        collection_name: str = "heritage_chunks",
        embedder: HashingEmbedder | None = None,
    ) -> None:
        self.path = path
        self.collection_name = collection_name
        self.embedder = embedder or HashingEmbedder()
        self._client = None
        self._collection = None

    @property
    def exists(self) -> bool:
        return self.count() > 0

    def count(self) -> int:
        try:
            return int(self._get_collection().count())
        except RuntimeError:
            raise
        except Exception:
            return 0

    def rebuild(self, chunks: Iterable[DocumentChunk]) -> int:
        self._require_chromadb()
        self.path.mkdir(parents=True, exist_ok=True)

        chunk_list = list(chunks)
        self._delete_collection_if_exists()
        collection = self._get_collection()
        self._upsert_chunks(collection, chunk_list)
        return len(chunk_list)

    def close(self) -> None:
        self._collection = None
        self._client = None
        if chromadb is None:
            return
        try:
            from chromadb.api.shared_system_client import SharedSystemClient

            SharedSystemClient.clear_system_cache()
        except Exception:
            pass

    def load(self) -> list[VectorRecord]:
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        result = collection.get(include=["documents", "metadatas", "embeddings"])
        records: list[VectorRecord] = []
        for index, record_id in enumerate(result.get("ids") or []):
            document = _at(result.get("documents"), index) or ""
            metadata = _at(result.get("metadatas"), index) or {}
            embedding = _normalize_embedding(_at(result.get("embeddings"), index))
            records.append(
                VectorRecord(
                    id=str(record_id),
                    text=str(document),
                    metadata=dict(metadata),
                    embedding=embedding,
                )
            )
        return records

    def similarity_search(self, query: str, top_k: int = 5) -> list[tuple[VectorRecord, float]]:
        if top_k <= 0:
            return []

        collection = self._get_collection()
        collection_count = collection.count()
        if collection_count == 0:
            return []

        result = collection.query(
            query_embeddings=[self.embedder.embed(query)],
            n_results=min(top_k, collection_count),
            include=["documents", "metadatas", "distances"],
        )
        ids = _first(result.get("ids")) or []
        documents = _first(result.get("documents")) or []
        metadatas = _first(result.get("metadatas")) or []
        distances = _first(result.get("distances")) or []

        matches: list[tuple[VectorRecord, float]] = []
        for index, record_id in enumerate(ids):
            distance = _at(distances, index)
            score = _cosine_distance_to_score(distance)
            matches.append(
                (
                    VectorRecord(
                        id=str(record_id),
                        text=str(_at(documents, index) or ""),
                        metadata=dict(_at(metadatas, index) or {}),
                        embedding=[],
                    ),
                    score,
                )
            )
        return matches

    def _get_client(self):
        self._require_chromadb()
        if self._client is None:
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.path))
        return self._client

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._get_client().get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _delete_collection_if_exists(self) -> None:
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None

    def _upsert_chunks(self, collection, chunks: list[DocumentChunk]) -> None:
        batch_size = 500
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            if not batch:
                continue
            collection.upsert(
                ids=[chunk.id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                metadatas=[_clean_metadata(chunk.metadata) for chunk in batch],
                embeddings=[self.embedder.embed(chunk.text) for chunk in batch],
            )

    @staticmethod
    def _require_chromadb() -> None:
        if chromadb is None:
            raise RuntimeError(
                "Chua cai chromadb. Hay chay: python -m pip install -r requirements.txt"
            )


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
            continue
        clean[key] = json.dumps(value, ensure_ascii=False)
    return clean


def _first(value):
    if not value:
        return None
    return value[0]


def _at(value, index: int):
    if value is None:
        return None
    try:
        return value[index]
    except (IndexError, TypeError):
        return None


def _normalize_embedding(value) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _cosine_distance_to_score(distance) -> float:
    if distance is None:
        return 0.0
    try:
        score = 1.0 - float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, score))


LocalVectorStore = ChromaVectorStore
