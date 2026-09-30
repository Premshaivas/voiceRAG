from __future__ import annotations

import json
from backend.answer_engine import GroundedAnswerEngine, REFUSAL
from backend.config import Settings
from backend.rag_engine import SearchResult


def test_low_confidence_retrieval_refuses_without_llm_call():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "Weak evidence", {"document_id": "doc"}, 0.99)]
    engine = GroundedAnswerEngine(Pipeline(), api_key="")
    result = engine.answer("Unrelated question")
    assert result["answer"] == REFUSAL
    assert result["grounded"] is False
    assert result["confidence"] == 0.0


def test_missing_gateway_returns_relevant_transcript_excerpt():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "A RAG system gives retrieved passages to a language model, which uses them to create a grounded answer.", {"document_id": "doc"}, 0.1)]

    engine = GroundedAnswerEngine(Pipeline(), api_key="")
    result = engine.answer("What does a RAG system do with retrieved passages?")

    assert result["answer_mode"] == "transcript_excerpt"
    assert result["grounded"] is True
    assert "retrieved passages" in result["answer"]
    assert result["citations"] == ["S1"]


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


def test_openai_compatible_provider_uses_configured_endpoint_and_bearer_auth():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "A RAG system retrieves relevant passages.", {"document_id": "doc"}, 0.1)]

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": "A RAG system retrieves relevant passages [S1]."}}]}).encode()

    config = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_api_key="test-provider-key",
        llm_api_base_url="https://llm.example.test/v1",
        llm_api_model="test-chat-model",
        answer_cache_max_entries=8,
        answer_cache_ttl_seconds=10,
    )
    observed = {}

    def opener(request, **kwargs):
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        observed["payload"] = json.loads(request.data)
        return Response()

    engine = GroundedAnswerEngine(Pipeline(), config=config, opener=opener)
    result = engine.answer("What does RAG retrieve?")

    assert observed["url"] == "https://llm.example.test/v1/chat/completions"
    assert observed["authorization"] == "Bearer test-provider-key"
    assert observed["payload"]["model"] == "test-chat-model"
    assert result["answer_mode"] == "llm"
    assert result["grounded"] is True


def test_openai_compatible_provider_failure_uses_transcript_excerpt():
    class Pipeline:
        def search(self, *args):
            return [SearchResult("c1", "The retrieval system finds passages about video transcription.", {"document_id": "doc"}, 0.1)]

    config = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_api_key="test-provider-key",
        llm_api_base_url="https://llm.example.test/v1",
        llm_api_model="test-chat-model",
        answer_cache_max_entries=8,
        answer_cache_ttl_seconds=10,
    )

    def opener(*args, **kwargs):
        raise OSError("provider unavailable")

    engine = GroundedAnswerEngine(Pipeline(), config=config, opener=opener)
    result = engine.answer("What about video transcription?")

    assert result["answer_mode"] == "transcript_excerpt"
    assert result["grounded"] is True
    assert "video transcription" in result["answer"]
