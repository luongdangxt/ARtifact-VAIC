"""Đối chiếu tài liệu đã dựng với tư liệu gốc để bắt chi tiết không có nguồn.

Bước 3 của pipeline. Prompt ở build_heritage_docs.py cấm Gemini thêm dữ kiện, nhưng
cấm không có nghĩa là nó tuân thủ tuyệt đối: model vẫn có thể chèn kiến thức nền của
riêng nó. Ví dụ thật đã gặp — tài liệu Quan họ xuất hiện cụm "hát vang, rền, nền,
nảy" trong khi cả hai nguồn crawl về đều không có chữ nào như vậy. Câu đó ĐÚNG,
nhưng đúng vì model biết sẵn chứ không phải vì tư liệu nói thế; với dataset di sản
thì đó chính là loại sai sót phải chặn.

Script kiểm hai nhóm dễ sai và dễ kiểm nhất:
  - Số: mọi con số trong tài liệu phải có trong tư liệu gốc.
  - Danh từ riêng: cụm từ viết hoa giữa câu (tên làng, tên người, tên làn điệu).

Đây là bộ lọc thô, không phải chứng minh: nó bắt được chi tiết bịa trắng trợn, còn
câu diễn giải sai sắc thái thì vẫn phải người đọc. Cảnh báo cần được xem là "phải
kiểm bằng mắt", không phải "chắc chắn sai" — số viết bằng chữ trong nguồn ("hai
gia đình") mà tài liệu viết bằng chữ số ("2") cũng sẽ bị nêu.

HAI GIỚI HẠN PHẢI NHỚ TRƯỚC KHI KẾT LUẬN MỘT CẢNH BÁO LÀ BỊA:

1. Hồ sơ UNESCO là tiếng Anh, tài liệu sinh ra là tiếng Việt, nên MỌI chi tiết dịch
   từ nguồn UNESCO đều bị báo. Đã gặp: "Cửu Long" (nguồn: Mekong), "Mẹ Đất"
   (Mother Earth), "Tết Trung Thu" (Mid-Autumn Festival), "72" (seventy-two),
   "dồn hãm, vang, rền, nảy" (restrained, resonant, ringing and staccato). Tất cả
   đều CÓ NGUỒN. Phải mở nguồn tiếng Anh ra đọc rồi mới kết luận.
2. Script chỉ soi số và danh từ riêng. Chi tiết bịa viết bằng từ thường, không viết
   hoa, không có số thì lọt lưới hoàn toàn.

Cách chạy:
    python scripts/verify_heritage_docs.py
    python scripts/verify_heritage_docs.py --only dan-ca-quan-ho-bac-ninh
    python scripts/verify_heritage_docs.py --quiet   # chỉ in tổng kết
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from heritage_registry import HERITAGES  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "dataset-raw"
DOCS_ROOT = PROJECT_ROOT / "heritage_ai" / "data" / "documents"

# Từ hay đứng đầu câu hoặc vốn luôn viết hoa -> viết hoa không có nghĩa là tên riêng.
STOPWORDS = {
    "Bên", "Các", "Cả", "Cách", "Còn", "Có", "Cùng", "Của", "Do", "Dù", "Dưới",
    "Hai", "Hầu", "Hiện", "Không", "Khi", "Kể", "Là", "Loại", "Lễ", "Mỗi", "Một",
    "Ngay", "Nghi", "Nghề", "Người", "Nhiều", "Những", "Nhạc", "Nội", "Nếu",
    "Ngoài", "Nghệ", "Sau", "Sự", "Theo", "Thời", "Trong", "Trên", "Trước", "Tuy",
    "Từ", "Tại", "Và", "Vào", "Với", "Vì", "Việc", "Đây", "Đó", "Đến", "Để",
    "Đầu", "Đồng", "Ông", "Bà", "Anh", "Chị", "Họ", "Nay", "Ban", "Bài", "Bản",
    "Hát", "Múa", "Tranh", "Giấy", "Màu", "Ván", "Di", "Sản", "Tín", "Thực",
    "Ngày", "Tháng", "Năm", "Phần", "Quy", "Tổ", "Đàn", "Lời", "Câu", "Trò",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalize(value: str) -> str:
    """So khớp nới lỏng: bỏ dấu, thường hoá, gộp khoảng trắng.

    Nguồn và tài liệu hay khác nhau ở dấu câu hoặc cách bỏ dấu tiếng Việt, so khớp
    thô sẽ báo động giả tràn lan.
    """
    return " ".join(strip_accents(value).casefold().split())


def load_raw(heritage_id: str) -> str:
    directory = RAW_ROOT / heritage_id
    manifest = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    parts = [
        (directory / source["file"]).read_text(encoding="utf-8")
        for source in manifest["sources"]
        if (directory / source["file"]).exists()
    ]
    return normalize("\n".join(parts))


def find_numbers(text: str) -> set[str]:
    # Bỏ số dính liền chữ (ví dụ mã quyết định) và số 1 chữ số vốn quá phổ biến.
    return {
        match
        for match in re.findall(r"(?<![\w.,])\d{2,}(?![\w])", text)
    }


PUNCT = ".,;:!?()\"'“”‘’-–—"


def _ends_phrase(word: str) -> bool:
    """Từ kết thúc bằng dấu câu -> cụm tên riêng dừng ở đây.

    Không có kiểm tra này thì một danh sách "Hà Giang, Quảng Ninh, Yên Bái" bị nối
    thành các cụm ma "Giang Quảng Ninh Yên" và bị báo là bịa.
    """
    return word.rstrip(PUNCT) != word


def find_proper_nouns(text: str) -> set[str]:
    """Cụm viết hoa KHÔNG đứng đầu câu — ứng viên tên riêng."""
    found: set[str] = set()
    for sentence in re.split(r"(?<=[.!?;:])\s+|\n+", text):
        words = sentence.split()
        # Bỏ từ đầu câu: viết hoa ở đó là do ngữ pháp, không phải tên riêng.
        for index, word in enumerate(words[1:], start=1):
            cleaned = word.strip(PUNCT)
            if not cleaned or not cleaned[0].isupper() or cleaned in STOPWORDS:
                continue
            if len(cleaned) < 2 or cleaned.isupper():
                continue
            # Gộp các từ viết hoa liền nhau thành một cụm ("Đường bạn Kim Loan"),
            # nhưng không vượt qua dấu câu.
            phrase = [cleaned]
            if not _ends_phrase(word):
                for nxt in words[index + 1 : index + 4]:
                    nxt_clean = nxt.strip(PUNCT)
                    if not nxt_clean or not nxt_clean[0].isupper():
                        break
                    if nxt_clean in STOPWORDS:
                        break
                    phrase.append(nxt_clean)
                    if _ends_phrase(nxt):
                        break
            found.add(" ".join(phrase))
    return found


def verify(heritage_id: str, name: str, quiet: bool) -> tuple[int, int]:
    raw = load_raw(heritage_id)
    documents = sorted(DOCS_ROOT.glob(f"{heritage_id}__*.md"))
    if not documents:
        print(f"  ! chưa dựng tài liệu cho {heritage_id}")
        return 0, 0

    flagged = 0
    checked = 0
    for path in documents:
        text = path.read_text(encoding="utf-8")
        problems: list[str] = []

        for number in sorted(find_numbers(text)):
            checked += 1
            if number not in raw:
                problems.append(f"số {number}")

        for phrase in sorted(find_proper_nouns(text)):
            checked += 1
            if normalize(phrase) not in raw:
                problems.append(f"tên riêng “{phrase}”")

        if problems:
            flagged += len(problems)
            if not quiet:
                print(f"  ⚠ {path.name}")
                for problem in problems:
                    print(f"      không có trong nguồn: {problem}")

    return flagged, checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", action="append", help="Chỉ kiểm heritage_id này.")
    parser.add_argument("--quiet", action="store_true", help="Chỉ in tổng kết.")
    args = parser.parse_args()

    targets = HERITAGES
    if args.only:
        wanted = set(args.only)
        targets = [item for item in HERITAGES if item["id"] in wanted]

    total_flagged = 0
    total_checked = 0
    dirty: list[str] = []
    for item in targets:
        if not args.quiet:
            print(f"[{item['name']}]")
        flagged, checked = verify(item["id"], item["name"], args.quiet)
        total_flagged += flagged
        total_checked += checked
        if flagged:
            dirty.append(f"{item['id']} ({flagged})")

    print(
        f"\nĐã kiểm {total_checked:,} chi tiết (số + tên riêng), "
        f"{total_flagged} chi tiết không tìm thấy trong tư liệu gốc."
    )
    if dirty:
        print("Cần soi lại: " + ", ".join(dirty))
    else:
        print("Không có chi tiết nào nằm ngoài tư liệu gốc.")


if __name__ == "__main__":
    main()
