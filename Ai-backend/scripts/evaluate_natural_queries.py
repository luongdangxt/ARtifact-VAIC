from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.pipeline import SmartHeritageLibrary, _build_persona, _contextualize_question


@dataclass(frozen=True)
class NaturalQueryCase:
    question: str
    persona_name: str
    persona_craft: str
    history: list[dict[str, str]] = field(default_factory=list)


CASES = [
    NaturalQueryCase("cái này là gì vậy", "Liền anh Quan họ", "Dân ca Quan họ Bắc Ninh"),
    NaturalQueryCase("ke nghe coi", "Ông đồ tranh Đông Hồ", "Tranh dân gian Đông Hồ"),
    NaturalQueryCase(
        "ở đâu á",
        "Liền anh Quan họ",
        "Dân ca Quan họ Bắc Ninh",
        [{"role": "user", "content": "Kể về Quan họ đi"}],
    ),
    NaturalQueryCase(
        "nó có gì hay",
        "Ông đồ tranh Đông Hồ",
        "Tranh dân gian Đông Hồ",
        [{"role": "user", "content": "Tranh Đông Hồ là gì?"}],
    ),
    NaturalQueryCase("có từ bao giờ", "Liền anh Quan họ", "Dân ca Quan họ Bắc Ninh"),
    NaturalQueryCase("ai hát vậy", "Liền anh Quan họ", "Dân ca Quan họ Bắc Ninh"),
    NaturalQueryCase("quan ho o dau v", "Liền anh Quan họ", "Dân ca Quan họ Bắc Ninh"),
    NaturalQueryCase("tranh nay lam kieu gi", "Ông đồ tranh Đông Hồ", "Tranh dân gian Đông Hồ"),
    NaturalQueryCase(
        "còn unesco thì sao",
        "Liền anh Quan họ",
        "Dân ca Quan họ Bắc Ninh",
        [{"role": "user", "content": "Quan họ thuộc loại hình gì?"}],
    ),
    NaturalQueryCase(
        "nói ngắn gọn thôi",
        "Ông đồ tranh Đông Hồ",
        "Tranh dân gian Đông Hồ",
        [{"role": "user", "content": "Giới thiệu tranh dân gian Đông Hồ"}],
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Đánh giá câu hỏi khẩu ngữ/câu cụt trên RAG thật.")
    parser.add_argument("--live", action="store_true", help="Gọi cả semantic router và LLM FPT thật.")
    parser.add_argument("--start", type=int, default=1, help="Vị trí test case bắt đầu (từ 1).")
    parser.add_argument("--limit", type=int, default=len(CASES), help="Số test case cần chạy.")
    args = parser.parse_args()

    pipeline = SmartHeritageLibrary.from_settings(Settings.from_env())
    start = max(0, args.start - 1)
    selected_cases = CASES[start : start + max(0, args.limit)]
    for index, case in enumerate(selected_cases, start=start + 1):
        persona = _build_persona(case.persona_name, case.persona_craft, None)
        resolved = _contextualize_question(case.question, case.history, persona)
        print(f"[{index}] USER: {case.question}")
        print(f"    RESOLVED: {resolved.replace(chr(10), ' | ')}")

        if args.live:
            response = pipeline.ask_text(
                case.question,
                synthesize=False,
                persona_name=case.persona_name,
                persona_craft=case.persona_craft,
                history=case.history,
            )
            print(f"    ALLOWED: {response.allowed}")
            print(f"    ANSWER: {response.answer}")
            print(f"    SOURCES: {[source.title for source in response.sources]}")
        else:
            sources = pipeline.retriever.retrieve(resolved)
            if not sources:
                print("    TOP: <none>")
            else:
                top = sources[0]
                print(
                    f"    TOP: {top.title} | {top.content_type} | score={top.score:.3f} | "
                    f"{top.text[:140].replace(chr(10), ' | ')}"
                )
                print(f"    ALL SOURCES: {[source.title for source in sources]}")
        print()


if __name__ == "__main__":
    main()
