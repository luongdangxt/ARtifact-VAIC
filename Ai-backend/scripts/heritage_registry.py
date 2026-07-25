"""Danh mục 17 di sản văn hóa phi vật thể Việt Nam được UNESCO ghi danh.

Đây là nguồn sự thật duy nhất cho pipeline đào dữ liệu:

    crawl_heritage_sources.py  đọc registry -> tải nguồn thật về dataset-raw/
    build_heritage_docs.py     đọc dataset-raw/ -> sinh tài liệu RAG có trích dẫn

`id` PHẢI giữ nguyên như trong heritage_ai/data/heritages.json với 5 di sản đã có
sẵn (Nhã nhạc, Quan họ, Bài Chòi, Đờn ca tài tử, Cồng chiêng). Đổi id sẽ tách một
di sản thành hai heritage_id khác nhau trong ChromaDB và làm hỏng bộ lọc truy xuất.

Mỗi `wiki_vi` đã được kiểm tra tồn tại trên vi.wikipedia.org (2026-07-25); phần tử
đầu tiên là bài chính, các phần tử sau là bài liên quan giúp bổ sung chi tiết.
`unesco` là trang hồ sơ chính thức trên ich.unesco.org.
"""

from __future__ import annotations

from typing import Any


# Loại danh sách của UNESCO: RL = Danh sách Đại diện của nhân loại,
# USL = Danh sách cần bảo vệ khẩn cấp.
HERITAGES: list[dict[str, Any]] = [
    {
        "id": "nha-nhac-cung-dinh-hue",
        "name": "Nhã nhạc cung đình Huế",
        "aliases": ["Nhã nhạc", "nhạc cung đình Huế", "Nhã nhạc - Âm nhạc Cung đình Việt Nam"],
        "unesco_year": 2008,
        "unesco_list": "RL",
        "wiki_vi": ["Nhã nhạc cung đình Huế"],
        "unesco": "https://ich.unesco.org/en/RL/nha-nhac-vietnamese-court-music-00074",
    },
    {
        "id": "khong-gian-van-hoa-cong-chieng-tay-nguyen",
        "name": "Không gian văn hóa Cồng chiêng Tây Nguyên",
        "aliases": ["Cồng chiêng Tây Nguyên", "văn hóa cồng chiêng"],
        "unesco_year": 2008,
        "unesco_list": "RL",
        "wiki_vi": [
            "Không gian văn hóa cồng chiêng Tây Nguyên",
            "Cồng chiêng",
            "Lễ hội Cồng chiêng",
        ],
        "unesco": "https://ich.unesco.org/en/RL/space-of-gong-culture-00120",
    },
    {
        "id": "dan-ca-quan-ho-bac-ninh",
        "name": "Dân ca Quan họ Bắc Ninh",
        "aliases": ["Quan họ", "hát Quan họ", "liền anh liền chị"],
        "unesco_year": 2009,
        "unesco_list": "RL",
        "wiki_vi": ["Quan họ"],
        "unesco": "https://ich.unesco.org/en/RL/quan-h-bc-ninh-folk-songs-00183",
    },
    {
        "id": "nghe-thuat-ca-tru",
        "name": "Nghệ thuật Ca trù",
        "aliases": ["Ca trù", "hát ca trù", "hát ả đào", "hát cô đầu"],
        "unesco_year": 2009,
        "unesco_list": "USL",
        "wiki_vi": ["Ca trù"],
        "unesco": "https://ich.unesco.org/en/USL/ca-tru-singing-00309",
    },
    {
        "id": "hoi-giong-den-phu-dong-va-den-soc",
        "name": "Hội Gióng ở đền Phù Đổng và đền Sóc",
        "aliases": ["Hội Gióng", "hội Gióng Phù Đổng", "Thánh Gióng"],
        "unesco_year": 2010,
        "unesco_list": "RL",
        "wiki_vi": ["Hội Gióng", "Thánh Gióng"],
        "unesco": "https://ich.unesco.org/en/RL/giong-festival-of-phu-djong-and-soc-temples-00443",
    },
    {
        "id": "tin-nguong-tho-cung-hung-vuong",
        "name": "Tín ngưỡng thờ cúng Hùng Vương ở Phú Thọ",
        "aliases": ["thờ cúng Hùng Vương", "giỗ Tổ Hùng Vương", "đền Hùng"],
        "unesco_year": 2012,
        "unesco_list": "RL",
        "wiki_vi": ["Tín ngưỡng thờ cúng Hùng Vương", "Đền Hùng", "Giỗ Tổ Hùng Vương"],
        "unesco": "https://ich.unesco.org/en/RL/worship-of-hung-kings-in-phu-th-00735",
    },
    {
        "id": "don-ca-tai-tu-nam-bo",
        "name": "Đờn ca tài tử Nam Bộ",
        "aliases": ["đờn ca tài tử", "tài tử Nam Bộ"],
        "unesco_year": 2013,
        "unesco_list": "RL",
        "wiki_vi": ["Đờn ca tài tử Nam Bộ"],
        "unesco": (
            "https://ich.unesco.org/en/RL/"
            "art-of-n-ca-tai-t-music-and-song-in-southern-viet-nam-00733"
        ),
    },
    {
        "id": "dan-ca-vi-giam-nghe-tinh",
        "name": "Dân ca Ví, Giặm Nghệ Tĩnh",
        "aliases": ["ví giặm", "dân ca ví dặm", "hát ví", "hát giặm"],
        "unesco_year": 2014,
        "unesco_list": "RL",
        "wiki_vi": ["Dân ca ví, giặm Nghệ Tĩnh"],
        "unesco": "https://ich.unesco.org/en/RL/vi-and-gim-folk-songs-of-ngh-tnh-01008",
    },
    {
        "id": "nghi-le-va-tro-choi-keo-co",
        "name": "Nghi lễ và trò chơi Kéo co",
        "aliases": ["kéo co", "kéo mỏ", "kéo song", "kéo co ngồi"],
        "unesco_year": 2015,
        "unesco_list": "RL",
        "wiki_vi": ["Kéo co"],
        "unesco": "https://ich.unesco.org/en/RL/tugging-rituals-and-games-01080",
    },
    {
        "id": "tin-nguong-tho-mau-tam-phu",
        "name": "Thực hành Tín ngưỡng thờ Mẫu Tam phủ của người Việt",
        "aliases": ["thờ Mẫu", "đạo Mẫu", "hầu đồng", "lên đồng", "hát chầu văn"],
        "unesco_year": 2016,
        "unesco_list": "RL",
        "wiki_vi": ["Tín ngưỡng thờ Mẫu Việt Nam"],
        "unesco": (
            "https://ich.unesco.org/en/RL/practices-related-to-the-viet-beliefs-"
            "in-the-mother-goddesses-of-three-realms-01064"
        ),
    },
    {
        "id": "nghe-thuat-bai-choi-trung-bo",
        "name": "Nghệ thuật Bài Chòi Trung Bộ Việt Nam",
        "aliases": ["Bài Chòi", "hô bài chòi", "hội bài chòi"],
        "unesco_year": 2017,
        "unesco_list": "RL",
        "wiki_vi": ["Bài chòi"],
        "unesco": "https://ich.unesco.org/en/RL/the-art-of-bai-choi-in-central-viet-nam-01222",
    },
    {
        "id": "hat-xoan-phu-tho",
        "name": "Hát Xoan Phú Thọ",
        "aliases": ["hát Xoan", "Xoan Phú Thọ", "hát cửa đình"],
        "unesco_year": 2017,
        "unesco_list": "RL",
        "wiki_vi": ["Hát xoan"],
        "unesco": "https://ich.unesco.org/en/RL/xoan-singing-of-phu-th-province-viet-nam-01260",
    },
    {
        "id": "thuc-hanh-then-tay-nung-thai",
        "name": "Thực hành Then của người Tày, Nùng, Thái",
        "aliases": ["nghi lễ Then", "hát Then", "Then Tày", "đàn tính"],
        "unesco_year": 2019,
        "unesco_list": "RL",
        "wiki_vi": ["Nghi lễ Then", "Hát then"],
        "unesco": (
            "https://ich.unesco.org/en/RL/practices-of-then-by-tay-nung-and-thai-"
            "ethnic-groups-in-viet-nam-01379"
        ),
    },
    {
        "id": "nghe-thuat-xoe-thai",
        "name": "Nghệ thuật Xòe Thái",
        "aliases": ["múa Xòe", "xòe Thái", "xòe vòng"],
        "unesco_year": 2021,
        "unesco_list": "RL",
        "wiki_vi": ["Xòe Thái"],
        "unesco": "https://ich.unesco.org/en/RL/art-of-xoe-dance-of-the-tai-people-in-viet-nam-01575",
    },
    {
        "id": "nghe-thuat-lam-gom-cua-nguoi-cham",
        "name": "Nghệ thuật làm gốm của người Chăm",
        "aliases": ["gốm Chăm", "gốm Bàu Trúc", "làng gốm Bàu Trúc"],
        "unesco_year": 2022,
        "unesco_list": "USL",
        "wiki_vi": ["Làng gốm Bàu Trúc", "Làng Chăm Mỹ Nghiệp"],
        "unesco": "https://ich.unesco.org/en/USL/art-of-pottery-making-of-chm-people-01574",
    },
    {
        "id": "le-hoi-via-ba-chua-xu-nui-sam",
        "name": "Lễ hội Vía Bà Chúa Xứ núi Sam",
        "aliases": ["vía Bà Chúa Xứ", "miếu Bà Chúa Xứ", "núi Sam", "Châu Đốc"],
        "unesco_year": 2024,
        "unesco_list": "RL",
        "wiki_vi": ["Lễ hội miếu Bà Chúa Xứ", "Miếu Bà Chúa Xứ Núi Sam", "Núi Sam"],
        "unesco": "https://ich.unesco.org/en/RL/festival-of-ba-chua-x-goddess-at-sam-mountain-01999",
    },
    {
        "id": "tranh-dan-gian-dong-ho",
        "name": "Nghề làm tranh dân gian Đông Hồ",
        "aliases": ["tranh Đông Hồ", "tranh dân gian Đông Hồ", "làng Đông Hồ", "giấy điệp"],
        "unesco_year": 2025,
        "unesco_list": "USL",
        "wiki_vi": ["Tranh Đông Hồ"],
        "unesco": (
            "https://ich.unesco.org/en/USL/craft-of-making-ong-h-folk-woodblock-printings-01737"
        ),
    },
]


UNESCO_LIST_LABEL = {
    "RL": "Danh sách Di sản văn hóa phi vật thể đại diện của nhân loại",
    "USL": "Danh sách Di sản văn hóa phi vật thể cần bảo vệ khẩn cấp",
}

# Các intent mà retriever hỗ trợ (heritage_ai/rag/retriever.py: INTENT_HINTS),
# cộng thêm "all" dùng làm wildcard cho tư liệu chi tiết không thuộc intent nào.
INTENTS: dict[str, str] = {
    "overview": "Khái quát",
    "history": "Nguồn gốc và lịch sử",
    "practice": "Cách thực hành và trình diễn",
    "meaning": "Ý nghĩa và giá trị văn hóa",
    "location": "Không gian văn hóa và địa bàn",
    "etiquette": "Lưu ý khi trải nghiệm",
    "all": "Chi tiết đặc sắc",
}


def get(heritage_id: str) -> dict[str, Any]:
    for item in HERITAGES:
        if item["id"] == heritage_id:
            return item
    raise KeyError(f"Không có di sản với id={heritage_id!r} trong registry.")


def ids() -> list[str]:
    return [item["id"] for item in HERITAGES]
