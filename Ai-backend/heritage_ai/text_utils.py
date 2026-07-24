"""Tiện ích chuẩn hóa tiếng Việt phục vụ tìm kiếm từ khóa."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())
