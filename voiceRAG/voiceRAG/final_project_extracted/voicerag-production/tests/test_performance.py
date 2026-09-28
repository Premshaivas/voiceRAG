from __future__ import annotations

import json
from types import SimpleNamespace

from backend.answer_engine import GroundedAnswerEngine
from backend.rag_engine import RAGPipeline, SearchResult
from tests.test_core import FakeClient


class CountingEmbedder:
    def __init__(self):
        self.calls = 0
    def encode(self, texts, **kwargs):
        self.calls += 1
        return [[1.0, float(len(text))] for text in texts]


def test_query_embedding_cache_reuses_identical_query():
    embedder = CountingEmbedder()
    pipeline = RAGPipeline(client=FakeClient(), embedder=embedder)
    pipeline.search("same query")
    pipeline.search("same query")
    assert embedder.calls == 1


def test_answer_cache_skips_duplicate_gateway_call():
    class Pipeline:
        def search(self, *args):
            return [SearchResult(id="c1", text="Evidence", metadata={"document_id":"doc-1"}, distance=0.1)]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"choices":[{"message":{"content":"Evidence [S1]"}}]}).encode()
    calls = {"count": 0}
    def opener(request, timeout=90):
        calls["count"] += 1
        return Response()
    engine = GroundedAnswerEngine(Pipeline(), api_key="key", opener=opener)
    first = engine.answer("What is the evidence?", owner_id="user-1")
    second = engine.answer("What is the evidence?", owner_id="user-1")
    assert first == second
    assert calls["count"] == 1
