"""Tạo catalog di sản tự động từ tên file trong thư mục dataset."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from heritage_ai.text_utils import normalize_text


DATASET_SOURCE = "Cục Di sản văn hóa – Danh mục di sản văn hóa phi vật thể quốc gia"
DATASET_SOURCE_URL = (
    "https://dsvh.gov.vn/danh-muc-di-san-van-hoa-phi-vat-the-quoc-gia-1789"
)


def extract_dataset_title(path: str | Path) -> str:
    title = re.sub(r"^\d+_", "", Path(path).stem).strip()
    return " ".join(title.split())


def slugify_title(title: str) -> str:
    slug = normalize_text(title).replace(" ", "-")
    return slug or "di-san-khong-ten"


def resolve_catalog_item(
    title: str,
    items: list[dict[str, Any]],
    allow_partial: bool = True,
) -> dict[str, Any] | None:
    normalized_title = normalize_text(title)
    exact_matches = []
    partial_matches: list[tuple[int, dict[str, Any]]] = []

    for item in items:
        aliases = [item["name"], *item.get("aliases", [])]
        for alias in aliases:
            normalized_alias = normalize_text(alias)
            if not normalized_alias:
                continue
            if normalized_alias == normalized_title:
                exact_matches.append(item)
                break
            if allow_partial and len(normalized_alias.split()) >= 2 and (
                normalized_alias in normalized_title
                or normalized_title in normalized_alias
            ):
                partial_matches.append((len(normalized_alias), item))

    if exact_matches:
        return exact_matches[0]
    if partial_matches:
        return max(partial_matches, key=lambda value: value[0])[1]
    return None


def merge_dataset_catalog(
    base_items: list[dict[str, Any]], dataset_directory: str | Path
) -> list[dict[str, Any]]:
    items = copy.deepcopy(base_items)
    directory = Path(dataset_directory)
    if not directory.exists():
        return items

    base_catalog = list(items)
    items_by_id = {item["id"]: item for item in items}
    for path in sorted(directory.rglob("*.pdf")):
        title = extract_dataset_title(path)
        item = resolve_catalog_item(title, items, allow_partial=False)
        if item is None:
            item = resolve_catalog_item(title, base_catalog, allow_partial=True)
        if item is None:
            heritage_id = slugify_title(title)
            item = items_by_id.get(heritage_id)
            if item is None:
                item = {
                    "id": heritage_id,
                    "name": title,
                    "aliases": [],
                    "sources": [DATASET_SOURCE],
                    "follow_up_questions": [
                        f"Nguồn gốc của {title} là gì?",
                        f"{title} được thực hành như thế nào?",
                        f"Giá trị văn hóa của {title} là gì?",
                    ],
                    "dataset_only": True,
                }
                items.append(item)
                items_by_id[heritage_id] = item
        if title != item["name"] and title not in item.setdefault("aliases", []):
            item["aliases"].append(title)

    return items
