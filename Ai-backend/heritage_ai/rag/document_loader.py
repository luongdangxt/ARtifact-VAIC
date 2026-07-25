"""Đọc tài liệu PDF/TXT/Markdown và dữ liệu di sản dạng JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from heritage_ai.dataset_catalog import (
    DATASET_SOURCE,
    DATASET_SOURCE_URL,
    extract_dataset_title,
    resolve_catalog_item,
    slugify_title,
)
from heritage_ai.rag.models import SourceDocument


class DocumentLoadError(RuntimeError):
    """Tài liệu không thể được nạp hoặc thiếu metadata bắt buộc."""


class DocumentLoader:
    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
    FIELD_LABELS = {
        "overview": "Khái quát",
        "history": "Nguồn gốc và lịch sử",
        "practice": "Cách thực hành",
        "meaning": "Giá trị văn hóa",
        "location": "Không gian văn hóa",
        "etiquette": "Lưu ý khi trải nghiệm",
        "visitor_tip": "Gợi ý dành cho du khách",
    }

    def load_directory(self, directory: str | Path) -> list[SourceDocument]:
        directory = Path(directory)
        if not directory.exists():
            return []

        documents: list[SourceDocument] = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in self.SUPPORTED_EXTENSIONS:
                continue
            metadata = self._load_metadata(path)
            if not metadata.get("heritage_id"):
                raise DocumentLoadError(
                    f"{path} thiếu heritage_id. Hãy tạo file metadata "
                    f"{path.name}.metadata.json."
                )
            documents.extend(self._load_file(path, metadata))
        return documents

    def load_heritage_json(self, json_path: str | Path) -> list[SourceDocument]:
        path = Path(json_path)
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocumentLoadError(f"Không đọc được {path}: {exc}") from exc

        documents: list[SourceDocument] = []
        for record in records:
            sources = record.get("sources") or ["Kho tri thức nội bộ"]
            for field, section in self.FIELD_LABELS.items():
                content = str(record.get(field, "")).strip()
                if not content:
                    continue
                source_index = -1 if field in {"location", "etiquette", "visitor_tip"} else 0
                source = sources[source_index]
                documents.append(
                    SourceDocument(
                        content=content,
                        heritage_id=record["id"],
                        heritage_name=record["name"],
                        source=source,
                        document_name=f"Kho tri thức: {record['name']}",
                        section=section,
                        intent="etiquette" if field == "visitor_tip" else field,
                        file_path=str(path),
                    )
                )
        return documents

    def load_dataset_directory(
        self,
        directory: str | Path,
        catalog: list[dict[str, Any]],
    ) -> list[SourceDocument]:
        directory = Path(directory)
        if not directory.exists():
            return []

        documents: list[SourceDocument] = []
        for path in sorted(directory.rglob("*.pdf")):
            title = extract_dataset_title(path)
            item = resolve_catalog_item(title, catalog)
            metadata = {
                "heritage_id": item["id"] if item else slugify_title(title),
                "heritage_name": item["name"] if item else title,
                "source": DATASET_SOURCE,
                "source_url": DATASET_SOURCE_URL,
                "document_name": path.name,
                "section": "Hồ sơ di sản",
                "intent": "all",
            }
            documents.extend(self._load_pdf(path, metadata))
        return documents

    def _load_file(
        self, path: Path, metadata: dict[str, Any]
    ) -> list[SourceDocument]:
        if path.suffix.casefold() == ".pdf":
            return self._load_pdf(path, metadata)

        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise DocumentLoadError(f"Không đọc được {path}: {exc}") from exc
        if not content:
            return []
        return [self._build_document(path, metadata, content, page=None)]

    def _load_pdf(
        self, path: Path, metadata: dict[str, Any]
    ) -> list[SourceDocument]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
        except Exception as exc:
            raise DocumentLoadError(f"Không đọc được PDF {path}: {exc}") from exc

        documents = []
        for page_number, page in enumerate(reader.pages, start=1):
            content = (page.extract_text() or "").strip()
            if content:
                documents.append(
                    self._build_document(path, metadata, content, page_number)
                )
        return documents

    @staticmethod
    def _load_metadata(path: Path) -> dict[str, Any]:
        candidates = (
            path.with_suffix(path.suffix + ".metadata.json"),
            path.with_suffix(".metadata.json"),
        )
        sidecar = next((candidate for candidate in candidates if candidate.exists()), None)
        if sidecar is None:
            return {}
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocumentLoadError(f"Metadata không hợp lệ {sidecar}: {exc}") from exc
        if not isinstance(data, dict):
            raise DocumentLoadError(f"Metadata {sidecar} phải là JSON object.")
        return data

    @staticmethod
    def _build_document(
        path: Path,
        metadata: dict[str, Any],
        content: str,
        page: int | None,
    ) -> SourceDocument:
        return SourceDocument(
            content=content,
            heritage_id=str(metadata["heritage_id"]),
            heritage_name=str(metadata.get("heritage_name", metadata["heritage_id"])),
            source=str(metadata.get("source", path.stem)),
            document_name=str(metadata.get("document_name", path.name)),
            page=page,
            section=str(metadata.get("section", path.stem)),
            intent=str(metadata.get("intent", "all")),
            source_url=str(metadata.get("source_url", "")),
            file_path=str(path),
        )
