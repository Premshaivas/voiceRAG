from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.answer_engine import GroundedAnswerEngine, REFUSAL
from backend.main import create_app
from backend.rag_engine import RAGPipeline, SearchResult


class FakeEmbedder:
    def encode(self, texts, **kwargs):
        return [[float(len(text)), 1.0] for text in texts]


class FakeCollection:
    def __init__(self):
        self.items = {}
    def upsert(self, ids, documents, embeddings, metadatas):
        self.items.update({i: (d, m) for i, d, m in zip(ids, documents, metadatas)})
    def delete(self, where):
        key = where.get("document_id")
        self.items = {i: v for i, v in self.items.items() if v[1].get("document_id") != key}
    def query(self, **kwargs):
        items = list(self.items.items())[: kwargs["n_results"]]
        return {"ids": [[i for i, _ in items]], "documents": [[v[0] for _, v in items]], "metadatas": [[v[1] for _, v in items]], "distances": [[0.1 for _ in items]]}


class FakeClient:
    def __init__(self):
        self.collection = FakeCollection()
    def get_or_create_collection(self, **kwargs):
        return self.collection


def test_chunking_and_indexing():
    pipeline = RAGPipeline(client=FakeClient(), embedder=FakeEmbedder(), chunk_size=30, chunk_overlap=5)
    ids = pipeline.add_document("This is the first sentence. This is the second sentence with more words.", {"document_id": "doc-1", "title": "Lecture"})
    assert ids
    assert pipeline.search("sentence", document_id="doc-1")[0].metadata["title"] == "Lecture"


def test_invalid_citations_are_not_grounded():
    assert GroundedAnswerEngine._valid_citations("Answer [S1] [S99]", 2) == {"S1"}


def test_health_upload_and_answer_flow(tmp_path, monkeypatch):
    from backend.config import Settings
    active = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db", upload_dir=str(tmp_path / "uploads"), chroma_dir=str(tmp_path / "chroma"))

    class FakeTranscriber:
        def transcribe(self, path):
            return SimpleNamespace(id="tr-1", text="The lecture explains vector search.", json_response={"language_code": "en", "speech_model_used": "universal-3-5-pro"})

    class FakePipeline:
        def add_document(self, text, metadata):
            return ["chunk-1"]

    class FakeAnswer:
        def answer(self, question, limit, document_id):
            return {"answer": "Vector search is explained. [S1]", "grounded": True, "citations": ["S1"], "sources": []}

    app = create_app(app_settings=active, pipeline=FakePipeline(), transcriber=FakeTranscriber(), answer_engine=FakeAnswer())
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/api/documents/upload", files={"file": ("lecture.wav", b"RIFFfake", "audio/wav")})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"
        answer = client.post("/api/answers", json={"question": "What is explained?"})
        assert answer.status_code == 200
        assert answer.json()["grounded"] is True
