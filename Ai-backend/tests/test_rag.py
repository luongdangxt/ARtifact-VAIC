import json
import tempfile
import unittest
from pathlib import Path

from heritage_ai.rag.document_loader import DocumentLoader
from heritage_ai.rag.embedding_client import LocalEmbedder
from heritage_ai.rag.models import SourceDocument, TextChunk
from heritage_ai.rag.text_chunker import TextChunker
from heritage_ai.rag.vector_store import ChromaVectorStore
from heritage_ai.dataset_catalog import merge_dataset_catalog


class RagTests(unittest.TestCase):
    def test_local_embedder_uses_e5_prefixes_and_normalization(self) -> None:
        class FakeVectors:
            def tolist(self):
                return [[0.1, 0.2]]

        class FakeEncoder:
            def __init__(self):
                self.calls = []

            def encode(self, texts, **options):
                self.calls.append((texts, options))
                return FakeVectors()

        encoder = FakeEncoder()
        embedder = LocalEmbedder(encoder=encoder)
        vector = embedder.embed_query("Bài Chòi xuất hiện từ bao giờ?")

        self.assertEqual(vector, [0.1, 0.2])
        self.assertTrue(encoder.calls[0][0][0].startswith("query: "))
        self.assertTrue(encoder.calls[0][1]["normalize_embeddings"])

    def test_dataset_catalog_groups_exact_duplicates_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "001_Lễ hội Cầu ngư.pdf").touch()
            (directory / "002_Lễ hội Cầu ngư.pdf").touch()
            (directory / "003_Lễ hội Cầu ngư ở Khánh Hòa.pdf").touch()
            catalog = merge_dataset_catalog([], directory)

        self.assertEqual(len(catalog), 2)

    def test_chunker_keeps_overlap_and_metadata(self) -> None:
        document = SourceDocument(
            content=" ".join(f"w{i}" for i in range(12)),
            heritage_id="bai-choi",
            heritage_name="Bài Chòi",
            source="Nguồn thử nghiệm",
            document_name="Tài liệu thử nghiệm",
        )
        chunks = TextChunker(max_words=5, overlap_words=2).split([document])

        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0].content.split()[-2:], chunks[1].content.split()[:2])
        self.assertEqual(chunks[0].heritage_id, "bai-choi")

    def test_loader_reads_text_with_sidecar_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            document = directory / "bai_choi.txt"
            document.write_text("Nội dung tài liệu.", encoding="utf-8")
            sidecar = directory / "bai_choi.txt.metadata.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "heritage_id": "bai-choi",
                        "heritage_name": "Bài Chòi",
                        "source": "Nguồn A",
                    }
                ),
                encoding="utf-8",
            )

            documents = DocumentLoader().load_directory(directory)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].source, "Nguồn A")

    def test_vector_store_filters_by_heritage(self) -> None:
        chunks = [
            TextChunk(
                id="a",
                content="Lịch sử Bài Chòi",
                heritage_id="bai-choi",
                heritage_name="Bài Chòi",
                source="Nguồn A",
                document_name="A",
                page=1,
                section="Lịch sử",
                intent="history",
            ),
            TextChunk(
                id="b",
                content="Lịch sử Quan họ",
                heritage_id="quan-ho",
                heritage_name="Quan họ",
                source="Nguồn B",
                document_name="B",
                page=2,
                section="Lịch sử",
                intent="history",
            ),
            TextChunk(
                id="c",
                content="Cách chơi Bài Chòi",
                heritage_id="bai-choi",
                heritage_name="Bài Chòi",
                source="Nguồn C",
                document_name="C",
                page=3,
                section="Thực hành",
                intent="practice",
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChromaVectorStore(temp_dir, collection_name="test_collection")
            store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
            evidence = store.search(
                [1.0, 0.0], "bai-choi", intent="history", top_k=3
            )

        # Di sản khác bị loại hẳn; intent chỉ ưu tiên mềm: chunk đúng intent xếp
        # trước nhưng chunk lệch intent tương đồng cao vẫn được giữ làm tư liệu.
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0].content, "Lịch sử Bài Chòi")
        self.assertEqual(evidence[1].content, "Cách chơi Bài Chòi")
        self.assertGreater(evidence[0].score, 0.9)

    def test_vector_store_rejects_embeddings_from_another_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = ChromaVectorStore(temp_dir, collection_name="model_check")
            old_store.upsert(
                [
                    TextChunk(
                        id="old",
                        content="Nội dung cũ",
                        heritage_id="bai-choi",
                        heritage_name="Bài Chòi",
                        source="Nguồn",
                        document_name="Tài liệu",
                        page=1,
                        section="Tổng quan",
                    )
                ],
                [[1.0, 0.0]],
            )

            with self.assertRaisesRegex(Exception, "--reset"):
                ChromaVectorStore(
                    temp_dir,
                    collection_name="model_check",
                    embedding_model="intfloat/multilingual-e5-base",
                )


if __name__ == "__main__":
    unittest.main()
