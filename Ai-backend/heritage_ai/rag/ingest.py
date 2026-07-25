"""CLI nhập dữ liệu vào ChromaDB bằng embedding chạy local."""

from __future__ import annotations

import argparse
from pathlib import Path

from tqdm.auto import tqdm

from heritage_ai.repository import HeritageRepository
from heritage_ai.rag.document_loader import DocumentLoader
from heritage_ai.rag.embedding_client import LocalEmbedder
from heritage_ai.rag.retriever import PROJECT_ROOT
from heritage_ai.rag.text_chunker import TextChunker
from heritage_ai.rag.vector_store import ChromaVectorStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nhập tài liệu vào kho RAG.")
    parser.add_argument(
        "--documents",
        type=Path,
        default=PROJECT_ROOT / "heritage_ai" / "data" / "documents",
        help="Thư mục chứa PDF, Markdown và TXT.",
    )
    parser.add_argument(
        "--heritages-json",
        type=Path,
        default=PROJECT_ROOT / "heritage_ai" / "data" / "heritages.json",
        help="Kho JSON được đưa vào index ban đầu.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "dataset",
        help="Thư mục dataset PDF được tự động suy ra metadata từ tên file.",
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=PROJECT_ROOT / "storage" / "chroma",
        help="Thư mục lưu ChromaDB.",
    )
    parser.add_argument("--no-json", action="store_true", help="Không ingest JSON mẫu.")
    parser.add_argument("--no-dataset", action="store_true", help="Không ingest thư mục dataset.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Số chunk mỗi batch embedding local (mặc định: 8).",
    )
    parser.add_argument("--reset", action="store_true", help="Tạo lại collection trước khi ingest.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    loader = DocumentLoader()
    documents = loader.load_directory(args.documents)
    if not args.no_json:
        documents.extend(loader.load_heritage_json(args.heritages_json))
    # PDF trong dataset/ chỉ là bản mô tả mẫu một trang, cùng khuôn cho mọi di sản.
    # Di sản nào đã được dựng lại bằng scripts/build_heritage_docs.py thì tư liệu
    # thật nằm trong data/documents/; giữ thêm trang mẫu chỉ khiến nó cạnh tranh
    # chỗ trong top_k (nó mang intent="all" nên lọt qua mọi bộ lọc intent).
    rebuilt_ids = {document.heritage_id for document in documents}
    if not args.no_dataset:
        repository = HeritageRepository(dataset_path=args.dataset)
        dataset_documents = loader.load_dataset_directory(
            args.dataset, repository.all()
        )
        kept = [
            document
            for document in dataset_documents
            if document.heritage_id not in rebuilt_ids
        ]
        documents.extend(kept)
        print(
            f"Dataset: {len(dataset_documents)} trang PDF, bỏ qua "
            f"{len(dataset_documents) - len(kept)} trang của "
            f"{len(rebuilt_ids)} di sản đã có tư liệu đầy đủ; "
            f"{len(repository.all())} tên di sản trong catalog."
        )
    if not documents:
        raise SystemExit("Không tìm thấy tài liệu để ingest.")

    chunks = TextChunker().split(documents)
    print(f"Đã đọc {len(documents)} phần tài liệu, tạo {len(chunks)} chunk.")

    embedder = LocalEmbedder()
    vector_store = ChromaVectorStore(
        args.storage,
        embedding_model=embedder.model,
        allow_embedding_mismatch=args.reset,
    )
    if args.reset:
        vector_store.reset()
    existing_ids = vector_store.existing_ids([chunk.id for chunk in chunks])
    pending_chunks = [chunk for chunk in chunks if chunk.id not in existing_ids]
    print(
        f"Đang tạo embedding local bằng {embedder.model} "
        f"(device={embedder.device}): {len(pending_chunks)} chunk mới, "
        f"bỏ qua {len(chunks) - len(pending_chunks)} chunk không đổi.",
        flush=True,
    )
    with tqdm(
        total=len(pending_chunks),
        desc="Embedding + ChromaDB",
        unit="chunk",
        dynamic_ncols=True,
    ) as progress:
        for start in range(0, len(pending_chunks), args.batch_size):
            batch = pending_chunks[start : start + args.batch_size]
            embeddings = embedder.embed_documents(batch, batch_size=args.batch_size)
            vector_store.upsert(batch, embeddings)
            progress.update(len(batch))
    print(
        f"Hoàn tất: đã upsert {len(pending_chunks)} chunk mới; "
        f"collection hiện có {vector_store.count()} chunk."
    )


if __name__ == "__main__":
    main()
