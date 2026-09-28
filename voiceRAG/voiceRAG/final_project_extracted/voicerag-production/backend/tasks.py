from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from .celery_app import celery_app
from .config import settings
from .db import Document, DocumentStatus, Transcript, create_database
from .malware_scanner import MalwareScanner
from .media_validation import validate_media
from .rag_engine import RAGPipeline
from .s3_storage import ObjectStorage
from .transcription import AssemblyAITranscriber


async def _process(document_id: str, object_key: str) -> dict[str, str]:
    engine, session_factory = create_database(settings.database_url)
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="voicerag-", suffix=Path(object_key).suffix, delete=False) as temp:
            path = temp.name
        ObjectStorage(settings).download(object_key, path)
        validate_media(path, settings)
        MalwareScanner(settings).scan(path)
        result = await asyncio.to_thread(AssemblyAITranscriber().transcribe, path)
        words = [{"text": getattr(word, "text", None), "start": getattr(word, "start", None), "end": getattr(word, "end", None)} for word in (getattr(result, "words", None) or [])]
        async with session_factory() as session:
            document = await session.get(Document, document_id)
            if not document:
                raise RuntimeError("Document no longer exists")
            metadata = {"document_id": document_id, "title": document.title, "assemblyai_transcript_id": result.id}
            if document.owner_id:
                metadata["owner_id"] = document.owner_id
        pipeline = RAGPipeline(persist_directory=settings.chroma_dir)
        await asyncio.to_thread(pipeline.add_document, result.text, metadata, words)
        raw = getattr(result, "json_response", {}) or {}
        async with session_factory() as session:
            document = await session.get(Document, document_id)
            document.status = DocumentStatus.completed
            session.add(Transcript(document_id=document_id, assemblyai_id=result.id, text=result.text, words_json=json.dumps(words), language_code=raw.get("language_code"), speech_model=raw.get("speech_model_used")))
            await session.commit()
        return {"document_id": document_id, "status": "completed"}
    except Exception as exc:
        async with session_factory() as session:
            document = await session.get(Document, document_id)
            if document:
                document.status, document.error = DocumentStatus.failed, str(exc)[:2000]
                await session.commit()
        raise
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
        await engine.dispose()


@celery_app.task(name="backend.tasks.process_document", bind=True, acks_late=True, reject_on_worker_lost=True)
def process_document(self, document_id: str, object_key: str) -> dict[str, str]:
    return asyncio.run(_process(document_id, object_key))
