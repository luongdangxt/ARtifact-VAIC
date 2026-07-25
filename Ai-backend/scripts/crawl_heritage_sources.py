"""Tải tư liệu gốc của 17 di sản UNESCO về thư mục dataset-raw/.

Bước 1 của pipeline đào dữ liệu. Script này CHỈ tải và lưu nguyên văn, không diễn
giải, không tóm tắt — để bước 2 (build_heritage_docs.py) có nguyên liệu kiểm chứng
được và mọi câu trong tài liệu RAG cuối cùng đều truy ngược được về một URL thật.

Nguồn:
  - vi.wikipedia.org qua MediaWiki API (action=query&prop=extracts) -> văn bản sạch.
  - ich.unesco.org: trang hồ sơ chính thức, HTML nên phải gỡ thẻ.

Kết quả:
    dataset-raw/<heritage_id>/wikipedia-vi__<title>.txt
    dataset-raw/<heritage_id>/unesco.txt
    dataset-raw/<heritage_id>/sources.json   <- provenance: url, ngày tải, số ký tự

Cách chạy:
    python scripts/crawl_heritage_sources.py                 # tải tất cả
    python scripts/crawl_heritage_sources.py --only tranh-dan-gian-dong-ho
    python scripts/crawl_heritage_sources.py --force         # tải lại cả file đã có
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from heritage_registry import HERITAGES, UNESCO_LIST_LABEL  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "dataset-raw"
USER_AGENT = "ARtifact-VAIC/1.0 (heritage RAG dataset builder)"
WIKI_API = "https://vi.wikipedia.org/w/api.php"

# Mục cuối bài Wikipedia không mang thông tin nội dung -> cắt bỏ trước khi lưu.
WIKI_DROP_SECTIONS = (
    "Xem thêm",
    "Tham khảo",
    "Chú thích",
    "Liên kết ngoài",
    "Ghi chú",
    "Nguồn",
    "Đọc thêm",
    "Thư mục",
    "Hình ảnh",
)


class _TextExtractor(HTMLParser):
    """Gỡ thẻ HTML, bỏ hẳn nội dung script/style/nav để lấy phần chữ đọc được."""

    SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "form"}
    BLOCK_TAGS = {
        "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "section", "article", "blockquote", "td",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        lines = [line.strip() for line in raw.split("\n")]
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def trim_wiki_extract(text: str) -> str:
    """Cắt bỏ phần tham khảo/liên kết ngoài ở cuối bài Wikipedia."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        heading = line.strip().strip("=").strip()
        if heading in WIKI_DROP_SECTIONS and line.strip().startswith("=="):
            return "\n".join(lines[:index]).strip()
    return text.strip()


def get_with_retry(
    session: requests.Session, url: str, params: dict | None = None, attempts: int = 5
) -> requests.Response:
    """GET có backoff. Wikipedia trả 429 khi crawl liên tục 17 di sản."""
    delay = 2.0
    for attempt in range(1, attempts + 1):
        response = session.get(url, params=params, timeout=60)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        if attempt == attempts:
            response.raise_for_status()
        wait = float(response.headers.get("Retry-After", delay))
        print(f"      · 429, chờ {wait:.0f}s rồi thử lại ({attempt}/{attempts - 1})")
        time.sleep(wait)
        delay *= 2
    raise RuntimeError("unreachable")


def fetch_wikipedia(title: str, session: requests.Session) -> tuple[str, str]:
    """Trả về (văn bản đã cắt gọn, URL chính tắc). Ném RuntimeError nếu thiếu bài."""
    response = get_with_retry(
        session,
        WIKI_API,
        {
            "action": "query",
            "prop": "extracts|info",
            "explaintext": 1,
            "exsectionformat": "wiki",
            "inprop": "url",
            "redirects": 1,
            "format": "json",
            "titles": title,
        },
    )
    pages = response.json()["query"]["pages"]
    page = next(iter(pages.values()))
    if "missing" in page or not page.get("extract"):
        raise RuntimeError(f"Wikipedia không có bài {title!r} hoặc bài rỗng.")
    return trim_wiki_extract(page["extract"]), page.get("fullurl", "")


def fetch_unesco(url: str, session: requests.Session) -> str:
    response = get_with_retry(session, url)
    text = html_to_text(response.text)
    # Trang ich.unesco.org có menu ngôn ngữ và cảnh báo trình duyệt rất dài phía
    # trên; phần mô tả hồ sơ thật bắt đầu ngay từ dòng "Inscribed in <năm>".
    marker = re.search(r"Inscribed in \d{4}", text)
    if marker:
        text = text[marker.start() :]
    return text.strip()


def write_source(
    directory: Path, filename: str, content: str, force: bool
) -> tuple[Path, bool]:
    path = directory / filename
    if path.exists() and not force:
        return path, False
    path.write_text(content, encoding="utf-8")
    return path, True


def crawl_heritage(
    item: dict, session: requests.Session, force: bool
) -> dict:
    directory = RAW_ROOT / item["id"]
    directory.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    sources: list[dict] = []

    for title in item["wiki_vi"]:
        try:
            text, url = fetch_wikipedia(title, session)
        except (RuntimeError, requests.RequestException) as exc:
            print(f"    ! Wikipedia {title!r}: {exc}")
            continue
        slug = re.sub(r"[^\w]+", "-", title, flags=re.UNICODE).strip("-")
        filename = f"wikipedia-vi__{slug}.txt"
        _, written = write_source(directory, filename, text, force)
        sources.append(
            {
                "file": filename,
                "source": f"Wikipedia tiếng Việt – {title}",
                "source_url": url or f"https://vi.wikipedia.org/wiki/{title}",
                "fetched_at": today,
                "chars": len(text),
            }
        )
        print(f"    {'+' if written else '=':>5} {filename} ({len(text):,} ký tự)")
        time.sleep(1.5)

    try:
        text = fetch_unesco(item["unesco"], session)
        _, written = write_source(directory, "unesco.txt", text, force)
        sources.append(
            {
                "file": "unesco.txt",
                "source": (
                    f"UNESCO – {UNESCO_LIST_LABEL[item['unesco_list']]} "
                    f"({item['unesco_year']})"
                ),
                "source_url": item["unesco"],
                "fetched_at": today,
                "chars": len(text),
            }
        )
        print(f"    {'+' if written else '=':>5} unesco.txt ({len(text):,} ký tự)")
    except requests.RequestException as exc:
        print(f"    ! UNESCO {item['unesco']}: {exc}")

    manifest = {
        "id": item["id"],
        "name": item["name"],
        "aliases": item["aliases"],
        "unesco_year": item["unesco_year"],
        "unesco_list": item["unesco_list"],
        "sources": sources,
    }
    (directory / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", action="append", help="Chỉ tải heritage_id này (lặp được).")
    parser.add_argument("--force", action="store_true", help="Ghi đè file đã tải.")
    args = parser.parse_args()

    targets = HERITAGES
    if args.only:
        wanted = set(args.only)
        targets = [item for item in HERITAGES if item["id"] in wanted]
        missing = wanted - {item["id"] for item in targets}
        if missing:
            raise SystemExit(f"Không có id trong registry: {', '.join(sorted(missing))}")

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    total_chars = 0
    for index, item in enumerate(targets, start=1):
        print(f"[{index}/{len(targets)}] {item['name']}")
        manifest = crawl_heritage(item, session, args.force)
        total_chars += sum(source["chars"] for source in manifest["sources"])

    print(
        f"\nXong: {len(targets)} di sản, {total_chars:,} ký tự tư liệu gốc "
        f"trong {RAW_ROOT.relative_to(PROJECT_ROOT)}/"
    )


if __name__ == "__main__":
    main()
