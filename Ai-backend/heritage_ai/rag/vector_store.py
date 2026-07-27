"""Lưu và tìm kiếm vector bằng ChromaDB cục bộ."""

from __future__ import annotations

import inspect
from pathlib import Path

from heritage_ai.models import Evidence
from heritage_ai.rag.models import TextChunk


class RagError(RuntimeError):
    """Lỗi cơ sở của pipeline RAG."""


class RagNotReadyError(RagError):
    """Vector database chưa được ingest."""


class RagNoEvidenceError(RagError):
    """Không tìm thấy đoạn tư liệu đủ liên quan."""


class ChromaVectorStore:
    COLLECTION_NAME = "heritage_knowledge"

    # Ưu tiên MỀM theo intent thay vì lọc cứng: tư liệu trả lời một câu hỏi không
    # phải lúc nào cũng nằm ở chunk gắn đúng intent — vd. từ nguyên của tên gọi
    # "Quan họ" nằm trong chunk history, nhưng câu "ý nghĩa của từ quan họ" bị
    # phân intent meaning; lọc cứng loại đúng đoạn cần thiết và chatbot trả lời
    # "chưa có tư liệu". Mức cộng lấy theo khoảng cách score "chắc chắn" đo ở
    # local_router (câu rõ ràng cách nhau 0.046-0.075): chunk lệch intent phải
    # liên quan hơn hẳn mới vượt được chunk đúng intent.
    INTENT_BONUS = 0.04

    def __init__(
        self,
        storage_path: str | Path,
        collection_name: str = COLLECTION_NAME,
        embedding_model: str | None = None,
        allow_embedding_mismatch: bool = False,
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RagError(
                "Chưa cài ChromaDB. Hãy chạy: pip install -r requirements.txt"
            ) from exc

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self._get_or_create_collection()
        if not allow_embedding_mismatch:
            self._validate_embedding_model()

    def _get_or_create_collection(self):
        names = {collection.name for collection in self.client.list_collections()}
        if self.collection_name in names:
            # Không truyền metadata vào get_or_create của ChromaDB 0.4.x vì bản
            # này có thể ghi đè metadata model của collection đang tồn tại.
            return self.client.get_collection(
                name=self.collection_name,
                embedding_function=None,
            )

        metadata = {}
        if self.embedding_model:
            metadata["embedding_model"] = self.embedding_model
        options = {"metadata": metadata or None}
        parameters = inspect.signature(
            self.client.get_or_create_collection
        ).parameters
        if "configuration" in parameters:
            options["configuration"] = {"hnsw": {"space": "cosine"}}
        else:
            # ChromaDB 0.4.x cấu hình metric qua collection metadata.
            metadata["hnsw:space"] = "cosine"
            options["metadata"] = metadata
        return self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
            **options,
        )

    def _validate_embedding_model(self) -> None:
        if not self.embedding_model:
            return
        metadata = self.collection.metadata or {}
        indexed_model = metadata.get("embedding_model")
        if self.collection.count() and indexed_model != self.embedding_model:
            indexed_label = indexed_model or "model cũ/không xác định"
            raise RagNotReadyError(
                f"VectorDB đang dùng {indexed_label}, nhưng ứng dụng đang dùng "
                f"{self.embedding_model}. Hãy tạo lại bằng: "
                "python3 create_vectorDB.py --reset"
            )
        if indexed_model != self.embedding_model:
            updated_metadata = dict(metadata)
            updated_metadata["embedding_model"] = self.embedding_model
            self.collection.modify(metadata=updated_metadata)

    def reset(self) -> None:
        names = {collection.name for collection in self.client.list_collections()}
        if self.collection_name in names:
            self.client.delete_collection(self.collection_name)
        self.collection = self._get_or_create_collection()

    def upsert(
        self, chunks: list[TextChunk], embeddings: list[list[float]]
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Số chunk và embedding phải bằng nhau.")
        if not chunks:
            return

        metadatas = []
        for chunk in chunks:
            metadata = {
                "heritage_id": chunk.heritage_id,
                "heritage_name": chunk.heritage_name,
                "source": chunk.source,
                "document_name": chunk.document_name,
                "section": chunk.section,
                "intent": chunk.intent,
                "file_path": chunk.file_path,
            }
            if chunk.page is not None:
                metadata["page"] = chunk.page
            if chunk.source_url:
                metadata["source_url"] = chunk.source_url
            metadatas.append(metadata)

        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: list[float],
        heritage_id: str,
        intent: str = "overview",
        top_k: int = 5,
        min_relevance: float = 0.15,
    ) -> list[Evidence]:
        if self.collection.count() == 0:
            raise RagNotReadyError(
                "Kho vector đang trống. Hãy chạy: "
                "python3 create_vectorDB.py --reset"
            )

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, top_k) * 3,
            where={"heritage_id": heritage_id},
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        scored: list[tuple[float, Evidence]] = []
        for chunk_id, content, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            relevance = 1.0 - float(distance)
            if relevance < min_relevance:
                continue
            chunk_intent = str(metadata.get("intent", "all"))
            boosted = relevance
            if intent != "overview" and chunk_intent in {intent, "all"}:
                boosted += self.INTENT_BONUS
            scored.append(
                (
                    boosted,
                    Evidence(
                        title=str(metadata.get("section", "Tư liệu truy xuất")),
                        content=content,
                        source=str(metadata.get("source", "Không rõ nguồn")),
                        page=int(metadata["page"]) if metadata.get("page") else None,
                        score=relevance,
                        source_url=str(metadata.get("source_url", "")),
                        document_name=str(metadata.get("document_name", "")),
                        chunk_id=chunk_id,
                    ),
                )
            )
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [evidence for _, evidence in scored[: max(1, top_k)]]

    def candidate_heritage_names(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        min_relevance: float = 0.05,
    ) -> list[str]:
        return [
            name
            for name, _ in self.rank_heritage_names(
                query_embedding, top_k=top_k, min_relevance=min_relevance
            )
        ]

    def rank_heritage_names(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        min_relevance: float = 0.05,
    ) -> list[tuple[str, float]]:
        """Như candidate_heritage_names nhưng giữ lại score (cosine similarity).

        Router local dùng khoảng cách giữa score hạng nhất và hạng nhì để biết mình
        có chắc chắn không — chắc thì khỏi gọi Gemini phân giải.
        """
        if self.collection.count() == 0:
            raise RagNotReadyError(
                "Kho vector đang trống. Hãy chạy: "
                "python3 create_vectorDB.py --reset"
            )
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, top_k),
            include=["metadatas", "distances"],
        )
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        scores: dict[str, float] = {}
        for metadata, distance in zip(metadatas, distances, strict=False):
            name = str(metadata.get("heritage_name", "")).strip()
            relevance = 1.0 - float(distance)
            if name and relevance >= min_relevance:
                scores[name] = max(scores.get(name, -1.0), relevance)
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def count(self) -> int:
        return self.collection.count()

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        result = self.collection.get(ids=ids, include=[])
        return set(result.get("ids") or [])
