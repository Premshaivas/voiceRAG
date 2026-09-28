from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.media_validation import validate_media
from backend.rate_limit import RateLimiter
from backend.session_tokens import token_hash


class FakeStorage:
    def __init__(self):
        self.completed = []
    def create_multipart(self, key, content_type):
        return "storage-upload-1"
    def presigned_part(self, key, upload_id, part_number):
        return f"https://storage.test/{part_number}"
    def complete_multipart(self, key, upload_id, parts):
        self.completed.append((key, upload_id, parts))


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client")
    assert limiter.allow("client")
    assert not limiter.allow("client")


def test_token_hash_is_deterministic():
    assert token_hash("abc") == token_hash("abc")
    assert token_hash("abc") != token_hash("def")


def test_multipart_presigning_and_completion(tmp_path):
    active = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db", upload_dir=str(tmp_path / "uploads"), chroma_dir=str(tmp_path / "chroma"))
    storage = FakeStorage()
    app = create_app(app_settings=active, pipeline=SimpleNamespace(), transcriber=SimpleNamespace(), answer_engine=SimpleNamespace(), storage=storage)
    with TestClient(app) as client:
        initiated = client.post("/api/uploads/initiate", json={"filename": "lecture.mp3", "content_type": "audio/mpeg", "size_bytes": 1024})
        assert initiated.status_code == 200, initiated.text
        upload_id = initiated.json()["upload_id"]
        assert client.get(f"/api/uploads/{upload_id}/parts").json()["parts"][0]["part_number"] == 1
        completed = client.post(f"/api/uploads/{upload_id}/complete", json={"parts": [{"part_number": 1, "etag": "etag-1"}]})
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "queued"
        assert storage.completed


def test_media_validation_accepts_allowed_audio(monkeypatch, tmp_path):
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    monkeypatch.setattr("backend.media_validation.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout='{"format":{"duration":"12"},"streams":[{"codec_type":"audio","codec_name":"mp3"}]}'))
    assert validate_media(media)["duration_seconds"] == 12
