from __future__ import annotations

import json
from backend.answer_engine import GroundedAnswerEngine, REFUSAL
from backend.rag_engine import SearchResult


def test_low_confidence_retrieval_refuses_without_llm_call():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "Weak evidence", {"document_id": "doc"}, 0.99)]
    engine = GroundedAnswerEngine(Pipeline(), api_key=None)
    result = engine.answer("Unrelated question")
    assert result["answer"] == REFUSAL
    assert result["grounded"] is False
    assert result["confidence"] == 0.0


def test_grounded_answer_reports_coverage_and_confidence():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "Evidence", {"document_id": "doc"}, 0.1)]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"choices":[{"message":{"content":"First claim [S1]. Second claim [S1]."}}]}).encode()
    engine = GroundedAnswerEngine(Pipeline(), api_key="key", opener=lambda *args, **kwargs: Response())
    result = engine.answer("What happened?", owner_id="user")
    assert result["grounded"] is True
    assert result["citation_coverage"] == 1.0
    assert result["confidence"] > 0.5
