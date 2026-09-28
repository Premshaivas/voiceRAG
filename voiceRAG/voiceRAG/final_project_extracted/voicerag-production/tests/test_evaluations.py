from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.rag_engine import SearchResult


class EvaluationPipeline:
    def search(self, query, limit=6, document_id=None, owner_id=None):
        return [SearchResult("chunk-1", "Deadlock requires mutual exclusion and hold-and-wait.", {"document_id": "doc-1", "title": "OS"}, 0.1)]


class EvaluationAnswer:
    def answer(self, question, limit=6, document_id=None, owner_id=None):
        return {"answer": "Deadlock requires mutual exclusion and hold-and-wait. [S1]", "grounded": True, "citations": ["S1"], "sources": [{"citation": "S1", "text": "Deadlock requires mutual exclusion and hold-and-wait.", "metadata": {"document_id": "doc-1", "title": "OS"}}]}


def test_evaluation_run_reports_retrieval_citation_answer_and_latency(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/evaluation.db", upload_dir=str(tmp_path / "uploads"), chroma_dir=str(tmp_path / "chroma"))
    app = create_app(app_settings=settings, pipeline=EvaluationPipeline(), answer_engine=EvaluationAnswer(), transcriber=SimpleNamespace(), storage=SimpleNamespace())
    with TestClient(app) as client:
        dataset = client.post("/api/evaluations/datasets", json={"name": "OS smoke"})
        assert dataset.status_code == 200
        dataset_id = dataset.json()["id"]
        case = client.post(f"/api/evaluations/datasets/{dataset_id}/cases", json={"question":"What causes deadlock?", "expected_answer":"Deadlock requires mutual exclusion and hold-and-wait.", "expected_document_ids":["doc-1"]})
        assert case.status_code == 200
        run = client.post(f"/api/evaluations/datasets/{dataset_id}/run")
        assert run.status_code == 200, run.text
        payload = run.json()
        assert payload["case_count"] == 1
        assert payload["metrics"]["retrieval_recall"] == 1.0
        assert payload["metrics"]["citation_precision"] == 1.0
        assert payload["metrics"]["citation_recall"] == 1.0
        assert payload["metrics"]["answer_f1"] > 0.9
        detail = client.get(f"/api/evaluations/runs/{payload['run_id']}")
        assert detail.status_code == 200
        assert len(detail.json()["results"]) == 1
