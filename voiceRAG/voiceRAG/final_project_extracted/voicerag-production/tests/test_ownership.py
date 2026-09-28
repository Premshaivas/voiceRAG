from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


class FakeTranscriber:
    def transcribe(self, path):
        return SimpleNamespace(id="tr-owner", text="Private lecture content.", json_response={})


class FakePipeline:
    def add_document(self, text, metadata):
        return ["chunk"]


class FakeAnswer:
    def answer(self, question, limit, document_id=None, owner_id=None):
        return {"answer": "Private answer [S1]", "grounded": True, "citations": ["S1"], "sources": [], "owner_id": owner_id}


def test_auth_required_and_owner_scoped_documents(tmp_path):
    active = Settings(auth_required=True, database_url=f"sqlite+aiosqlite:///{tmp_path}/owners.db", upload_dir=str(tmp_path / "uploads"), chroma_dir=str(tmp_path / "chroma"))
    app = create_app(app_settings=active, pipeline=FakePipeline(), transcriber=FakeTranscriber(), answer_engine=FakeAnswer())
    with TestClient(app) as client:
        assert client.get("/api/documents").status_code == 401
        first = client.post("/api/auth/register", json={"email":"one@example.com", "password":"password1"})
        assert first.status_code == 200, first.text
        first_token = first.json()["access_token"]
        uploaded = client.post("/api/documents/upload", headers={"Authorization": f"Bearer {first_token}"}, files={"file": ("private.wav", b"RIFF", "audio/wav")})
        assert uploaded.status_code == 200, uploaded.text
        document_id = uploaded.json()["id"]
        playback = client.get(f"/api/documents/{document_id}/audio", headers={"Authorization": f"Bearer {first_token}"})
        assert playback.status_code == 200
        assert playback.content == b"RIFF"
        second = client.post("/api/auth/register", json={"email":"two@example.com", "password":"password2"})
        second_token = second.json()["access_token"]
        listed = client.get("/api/documents", headers={"Authorization": f"Bearer {second_token}"})
        assert listed.status_code == 200
        assert listed.json() == []
        forbidden = client.post("/api/answers", headers={"Authorization": f"Bearer {second_token}"}, json={"question":"What is private?", "document_id":document_id})
        assert forbidden.status_code == 404
