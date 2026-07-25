"""Biến tư liệu gốc trong dataset-raw/ thành tài liệu RAG có trích dẫn.

Bước 2 của pipeline đào dữ liệu. Gemini ở đây KHÔNG sáng tác: nó chỉ đọc tư liệu
đã crawl rồi cắt và sắp xếp lại theo 7 intent mà retriever dùng để lọc. Prompt cấm
thêm dữ kiện ngoài tư liệu, và mỗi mục phải khai báo nó lấy từ nguồn [S#] nào —
nhờ vậy `source_url` trong metadata là URL thật, không phải nhãn dán.

Vì sao phải qua LLM: tư liệu gốc trộn lẫn mọi khía cạnh trong một bài văn xuôi,
trong khi ChromaDB lọc chunk theo trường `intent`. Không tách theo intent thì câu
hỏi "có từ bao giờ" vẫn kéo về đoạn nói chuyện trang phục.

Đầu ra:
    heritage_ai/data/documents/<id>__<intent>.md            <- nội dung cho RAG
    heritage_ai/data/documents/<id>__<intent>.md.metadata.json
    heritage_ai/data/heritages.json                         <- catalog rút gọn 17 di sản

Cách chạy:
    python scripts/build_heritage_docs.py
    python scripts/build_heritage_docs.py --only tranh-dan-gian-dong-ho
    python scripts/build_heritage_docs.py --model gemini-3.1-pro-preview
    python scripts/build_heritage_docs.py --no-catalog        # không đụng heritages.json

Sau khi chạy xong phải tạo lại VectorDB:
    python create_vectorDB.py --reset
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from heritage_registry import HERITAGES, INTENTS, UNESCO_LIST_LABEL  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "dataset-raw"
DOCS_ROOT = PROJECT_ROOT / "heritage_ai" / "data" / "documents"
CATALOG_PATH = PROJECT_ROOT / "heritage_ai" / "data" / "heritages.json"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Model mặc định cố ý MẠNH hơn model chạy runtime (flash-lite trong .env): đây là
# job offline chạy một lần, chất lượng tách intent quan trọng hơn tốc độ/chi phí.
DEFAULT_MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """\
Bạn là biên tập viên tư liệu di sản văn hóa phi vật thể Việt Nam.

Nhiệm vụ: đọc các đoạn tư liệu được đánh số [S1], [S2]... rồi SẮP XẾP LẠI nội dung
thành các mục theo chủ đề. Đây là công việc biên tập, KHÔNG phải sáng tác.

Quy tắc bắt buộc:
1. TUYỆT ĐỐI không thêm bất kỳ dữ kiện nào không có trong tư liệu. Không suy đoán,
   không "bổ sung kiến thức nền", không viết câu chung chung kiểu "di sản góp phần
   làm phong phú bản sắc dân tộc".
   Bạn CÓ THỂ đã biết sẵn nhiều điều nổi tiếng về di sản này. Nếu tư liệu không
   nhắc tới thì KHÔNG được đưa vào, kể cả khi bạn chắc chắn nó đúng. Tài liệu này
   phải truy ngược được về nguồn đã dẫn, nên một câu đúng mà không có nguồn vẫn là
   lỗi. Ví dụ lỗi đã gặp: thêm tên kỹ thuật hát, thêm số lượng bài bản, thêm thời
   điểm diễn ra trong năm — trong khi tư liệu không hề nêu.
2. Giữ NGUYÊN VĂN mọi con số, tên riêng, tên làng, tên nhạc cụ, mốc thời gian,
   thuật ngữ chuyên ngành có trong tư liệu. Đây là phần giá trị nhất.
   Chép đúng chính tả tên riêng như tư liệu viết: "Đắk Lắk" không được đổi thành
   "Đắc Lắc", "gỗ thừng mực" không được đổi thành "gỗ thúng mụn".
3. Tư liệu tiếng Anh (hồ sơ UNESCO) thì dịch sang tiếng Việt sát nghĩa, giữ nguyên
   số liệu và tên riêng.
4. Nếu tư liệu không đủ cho một mục, hãy viết ngắn hoặc để chuỗi rỗng. Mục rỗng tốt
   hơn mục bịa. Không lặp lại nội dung của mục khác cho đủ độ dài.
5. Viết văn xuôi liền mạch, giọng kể tự nhiên cho hướng dẫn viên đọc cho du khách.
   Không dùng gạch đầu dòng, không markdown, không tiêu đề con trong nội dung.
6. TUYỆT ĐỐI không nhắc tới bản thân tư liệu. Cấm các câu như "Theo tư liệu...",
   "Bài viết cho biết...", "Tư liệu không nêu...", "Không có thông tin về...".
   Nội dung sẽ được nhân vật ảo đọc thành tiếng cho du khách nghe, nên chỉ được
   chứa lời kể về di sản. Thiếu tư liệu thì viết ngắn lại, không giải thích vì sao.
7. Mỗi mục phải khai báo `source_ids` gồm số của các nguồn [S#] mà mục đó lấy từ.

Các mục cần viết (dùng đúng khóa intent):
- overview: khái quát di sản là gì, đặc điểm nhận diện nổi bật nhất.
- history: nguồn gốc, truyền thuyết, các mốc lịch sử, quá trình được công nhận.
- practice: cách thực hành/trình diễn/chế tác cụ thể — quy trình, kỹ thuật, nhạc cụ,
  vật liệu, vai trò từng người, trình tự nghi lễ. Đây là mục cần chi tiết nhất.
- meaning: ý nghĩa, giá trị văn hóa - xã hội, vai trò trong đời sống cộng đồng.
- location: địa bàn thực hành, làng/đền/tỉnh cụ thể, thời điểm diễn ra trong năm.
- etiquette: điều du khách nên và không nên làm khi tới xem hoặc trải nghiệm. Chỉ
  viết những gì suy ra trực tiếp được từ tư liệu về tính chất nghi lễ, không khuyên
  chung chung.
- all: chi tiết đặc sắc còn lại chưa xếp được vào mục nào — thuật ngữ, tên làn điệu,
  tên tác phẩm, giai thoại, câu ca, con số đáng nhớ. Mục này để chatbot có cái kể
  khi du khách hỏi sâu.

Ngoài ra viết `summary` — bản rút gọn 1-2 câu cho từng mục overview/history/practice/
meaning/location/etiquette, dùng làm thẻ tóm tắt.

Và `follow_up_questions`: đúng 3 câu hỏi tiếng Việt mà du khách có thể hỏi tiếp, và
tư liệu hiện có TRẢ LỜI ĐƯỢC.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": list(INTENTS.keys()),
                    },
                    "content": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["intent", "content", "source_ids"],
                "propertyOrdering": ["intent", "content", "source_ids"],
            },
        },
        "summary": {
            "type": "object",
            "properties": {
                "overview": {"type": "string"},
                "history": {"type": "string"},
                "practice": {"type": "string"},
                "meaning": {"type": "string"},
                "location": {"type": "string"},
                "etiquette": {"type": "string"},
            },
            "required": [
                "overview",
                "history",
                "practice",
                "meaning",
                "location",
                "etiquette",
            ],
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections", "summary", "follow_up_questions"],
    "propertyOrdering": ["sections", "summary", "follow_up_questions"],
}


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    pairs = re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", path.read_text("utf-8"), re.M)
    return {key: value.strip().strip('"').strip("'") for key, value in pairs}


def read_manifest(heritage_id: str) -> dict:
    path = RAW_ROOT / heritage_id / "sources.json"
    if not path.exists():
        raise SystemExit(
            f"Thiếu {path}. Chạy scripts/crawl_heritage_sources.py trước."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(item: dict, manifest: dict) -> tuple[str, list[dict]]:
    directory = RAW_ROOT / item["id"]
    blocks: list[str] = []
    used: list[dict] = []
    for source in manifest["sources"]:
        text = (directory / source["file"]).read_text(encoding="utf-8").strip()
        if not text:
            continue
        index = len(used) + 1
        used.append(source)
        blocks.append(
            f"[S{index}] Nguồn: {source['source']}\nURL: {source['source_url']}\n\n{text}"
        )

    header = (
        f"DI SẢN: {item['name']}\n"
        f"UNESCO ghi danh năm {item['unesco_year']} — "
        f"{UNESCO_LIST_LABEL[item['unesco_list']]}.\n"
        f"Tên gọi khác: {', '.join(item['aliases'])}.\n"
    )
    body = "\n\n" + ("\n\n" + "=" * 70 + "\n\n").join(blocks)
    return header + body, used


def call_gemini(
    api_key: str, model: str, prompt: str, attempts: int = 4
) -> dict:
    url = f"{API_BASE}/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 32768,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    delay = 8.0
    for attempt in range(1, attempts + 1):
        response = requests.post(
            url, params={"key": api_key}, json=payload, timeout=600
        )
        if response.status_code in (429, 500, 502, 503, 504):
            if attempt == attempts:
                raise RuntimeError(
                    f"Gemini {response.status_code} sau {attempts} lần: "
                    f"{response.text[:300]}"
                )
            print(f"      · {response.status_code}, chờ {delay:.0f}s rồi thử lại")
            time.sleep(delay)
            delay *= 2
            continue
        if not response.ok:
            raise RuntimeError(f"Gemini {response.status_code}: {response.text[:500]}")

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini không trả candidate: {json.dumps(data)[:400]}")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            reason = candidates[0].get("finishReason", "?")
            raise RuntimeError(f"Gemini trả rỗng (finishReason={reason}).")
        return json.loads(text)
    raise RuntimeError("unreachable")


def write_documents(item: dict, result: dict, sources: list[dict]) -> list[Path]:
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for section in result["sections"]:
        intent = section["intent"]
        content = section["content"].strip()
        if len(content) < 80:
            print(f"      · bỏ qua intent={intent}: tư liệu không đủ ({len(content)} ký tự)")
            continue

        picked = [
            sources[index - 1]
            for index in section.get("source_ids", [])
            if 1 <= index <= len(sources)
        ] or sources

        stem = f"{item['id']}__{intent}"
        doc_path = DOCS_ROOT / f"{stem}.md"
        doc_path.write_text(content + "\n", encoding="utf-8")
        (DOCS_ROOT / f"{stem}.md.metadata.json").write_text(
            json.dumps(
                {
                    "heritage_id": item["id"],
                    "heritage_name": item["name"],
                    "source": " | ".join(dict.fromkeys(s["source"] for s in picked)),
                    "source_url": picked[0]["source_url"],
                    "document_name": f"{item['name']} — {INTENTS[intent]}",
                    "section": INTENTS[intent],
                    "intent": intent,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(doc_path)
        print(f"      + {stem}.md ({len(content):,} ký tự, {len(picked)} nguồn)")

    return written


def catalog_entry(item: dict, result: dict, sources: list[dict]) -> dict:
    summary = result["summary"]
    return {
        "id": item["id"],
        "name": item["name"],
        "aliases": item["aliases"],
        "overview": summary["overview"].strip(),
        "history": summary["history"].strip(),
        "practice": summary["practice"].strip(),
        "meaning": summary["meaning"].strip(),
        "location": summary["location"].strip(),
        "etiquette": summary["etiquette"].strip(),
        "visitor_tip": summary["etiquette"].strip(),
        "unesco_year": item["unesco_year"],
        "unesco_list": UNESCO_LIST_LABEL[item["unesco_list"]],
        "sources": list(dict.fromkeys(source["source"] for source in sources)),
        "source_urls": list(dict.fromkeys(source["source_url"] for source in sources)),
        "follow_up_questions": [q.strip() for q in result["follow_up_questions"][:3]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", action="append", help="Chỉ dựng heritage_id này (lặp được).")
    parser.add_argument("--model", default=None, help=f"Model Gemini (mặc định {DEFAULT_MODEL}).")
    parser.add_argument(
        "--no-catalog", action="store_true", help="Không ghi lại heritages.json."
    )
    args = parser.parse_args()

    env = load_env(PROJECT_ROOT / ".env")
    api_key = os.getenv("GEMINI_API_KEY") or env.get("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("Chưa có GEMINI_API_KEY trong môi trường hoặc .env.")
    model = args.model or os.getenv("BUILD_MODEL") or DEFAULT_MODEL

    targets = HERITAGES
    if args.only:
        wanted = set(args.only)
        targets = [item for item in HERITAGES if item["id"] in wanted]
        missing = wanted - {item["id"] for item in targets}
        if missing:
            raise SystemExit(f"Không có id trong registry: {', '.join(sorted(missing))}")

    print(f"Model: {model}\n")
    entries: list[dict] = []
    failures: list[str] = []

    for index, item in enumerate(targets, start=1):
        print(f"[{index}/{len(targets)}] {item['name']}")
        manifest = read_manifest(item["id"])
        prompt, sources = build_prompt(item, manifest)
        print(f"      tư liệu gốc: {len(prompt):,} ký tự từ {len(sources)} nguồn")
        try:
            result = call_gemini(api_key, model, prompt)
        except (RuntimeError, json.JSONDecodeError, requests.RequestException) as exc:
            print(f"    ! THẤT BẠI: {exc}")
            failures.append(item["id"])
            continue
        write_documents(item, result, sources)
        entries.append(catalog_entry(item, result, sources))

    if entries and not args.no_catalog:
        existing = (
            json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            if CATALOG_PATH.exists()
            else []
        )
        merged = {record["id"]: record for record in existing}
        merged.update({record["id"]: record for record in entries})
        ordered = [merged[item["id"]] for item in HERITAGES if item["id"] in merged]
        ordered += [
            record for key, record in merged.items()
            if key not in {item["id"] for item in HERITAGES}
        ]
        CATALOG_PATH.write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nĐã ghi {CATALOG_PATH.relative_to(PROJECT_ROOT)} ({len(ordered)} di sản).")

    print(f"\nXong: {len(entries)}/{len(targets)} di sản.")
    if failures:
        print("Thất bại: " + ", ".join(failures))
    print("Bước tiếp theo: python create_vectorDB.py --reset")


if __name__ == "__main__":
    main()
