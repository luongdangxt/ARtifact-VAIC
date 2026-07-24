"""Kho tri thức cục bộ và cơ chế truy xuất di sản."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from heritage_ai.dataset_catalog import merge_dataset_catalog
from heritage_ai.text_utils import normalize_text


class HeritageRepository:
    def __init__(
        self,
        data_path: str | Path | None = None,
        dataset_path: str | Path | None = None,
        include_dataset: bool = True,
    ) -> None:
        default_path = Path(__file__).parent / "data" / "heritages.json"
        self.data_path = Path(data_path) if data_path else default_path
        with self.data_path.open(encoding="utf-8") as file:
            self._items: list[dict[str, Any]] = json.load(file)
        if include_dataset:
            project_root = Path(__file__).resolve().parent.parent
            dataset_directory = (
                Path(dataset_path) if dataset_path else project_root / "dataset"
            )
            self._items = merge_dataset_catalog(self._items, dataset_directory)

    def all(self) -> list[dict[str, Any]]:
        return list(self._items)

    def find(self, query: str) -> dict[str, Any] | None:
        normalized_query = normalize_text(query)
        query_tokens = set(normalized_query.split())
        best_item: dict[str, Any] | None = None
        best_score = 0

        for item in self._items:
            aliases = [item["name"], *item.get("aliases", [])]
            normalized_aliases = [normalize_text(alias) for alias in aliases]

            score = 0
            for alias in normalized_aliases:
                if alias and alias in normalized_query:
                    score = max(score, 100 + len(alias.split()))
                else:
                    alias_tokens = set(alias.split())
                    overlap = len(query_tokens & alias_tokens)
                    score = max(score, overlap)

            if score > best_score:
                best_item = item
                best_score = score

        # Một từ chung như "nghệ thuật" không đủ để xác định di sản.
        return best_item if best_score >= 2 else None
