from __future__ import annotations

import hashlib
import math
import re
import unicodedata


TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)

STOPWORDS = {
    "và",
    "là",
    "của",
    "có",
    "cho",
    "với",
    "trong",
    "một",
    "những",
    "các",
    "được",
    "này",
    "đó",
    "the",
    "and",
    "of",
    "to",
}


class HashingEmbedder:
    """Small deterministic embedder for local/offline retrieval.

    It is not a replacement for a trained embedding model, but it gives the
    project a runnable vector database without downloading dependencies.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokens(text)
        features = tokens + self._bigrams(tokens)

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = 1.0 if (value >> 8) % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            return vector
        return [item / norm for item in vector]

    def _tokens(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFC", text.lower())
        tokens = TOKEN_RE.findall(normalized)
        clean_tokens = [token for token in tokens if len(token) > 1 and token not in STOPWORDS]
        expanded: list[str] = []
        for token in clean_tokens:
            expanded.append(token)
            plain = strip_vietnamese_accents(token)
            if plain != token:
                expanded.append(plain)
        return expanded

    @staticmethod
    def _bigrams(tokens: list[str]) -> list[str]:
        return [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def strip_vietnamese_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")
