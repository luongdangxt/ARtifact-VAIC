from __future__ import annotations

import re


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def chunk_text(text: str, chunk_size_words: int = 260, overlap_words: int = 60) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return []

    words = clean.split(" ")
    if len(words) <= chunk_size_words:
        return [clean]

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size_words - overlap_words)

    while start < len(words):
        end = min(len(words), start + chunk_size_words)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start += step

    return chunks
