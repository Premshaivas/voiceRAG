from __future__ import annotations

from backend.config import Settings
from backend.main import create_app


def test_local_audio_range_response(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend.db import Document, DocumentStatus

    active = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/audio.db", upload_dir=str(tmp_path), chroma_dir=str(tmp_path / "chroma"), auth_required=False)
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"0123456789")
    class Storage: pass
    app = create_app(app_settings=active, pipeline=SimpleNamespace(), transcriber=SimpleNamespace(), answer_engine=SimpleNamespace(), storage=Storage())
    async def seed():
        async with app.state.session_factory() as session:
            session.add(Document(id="audio-doc", title="Clip", filename="clip.wav", storage_path=str(audio), status=DocumentStatus.completed))
            await session.commit()
    with TestClient(app) as client:
        asyncio.run(seed())
        response = client.get("/api/documents/audio-doc/audio", headers={"Range": "bytes=2-5"})
        assert response.status_code == 206
        assert response.content == b"2345"
        assert response.headers["content-range"] == "bytes 2-5/10"
