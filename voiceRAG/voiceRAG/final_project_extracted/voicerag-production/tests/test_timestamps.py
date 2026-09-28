from __future__ import annotations

from backend.rag_engine import RAGPipeline
from tests.test_core import FakeClient, FakeEmbedder


def test_word_timestamp_metadata_is_indexed():
    pipeline = RAGPipeline(client=FakeClient(), embedder=FakeEmbedder(), chunk_size=40, chunk_overlap=8)
    pipeline.add_document("First point. Second point.", {"document_id": "doc-time"}, words=[{"text":"First", "start":100, "end":500}, {"text":"point.", "start":500, "end":900}, {"text":"Second", "start":1200, "end":1600}, {"text":"point.", "start":1600, "end":2000}])
    results = pipeline.search("point", document_id="doc-time")
    assert results
    assert results[0].metadata["start_ms"] == 100
    assert results[0].metadata["end_ms"] == 2000
