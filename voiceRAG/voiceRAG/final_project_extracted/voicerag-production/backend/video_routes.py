"""Routes for video import (file upload or URL) and key-points extraction."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request as FastAPIRequest, UploadFile
from pydantic import BaseModel, Field

from .auth import get_current_user
from .config import settings
from .db import Document, DocumentStatus, Transcript, User

router = APIRouter(prefix="/api", tags=["video"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VideoURLRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000, description="Video URL (YouTube, direct link, etc.)")
    title: str | None = Field(default=None, max_length=500, description="Optional custom title")


class KeyPointsResponse(BaseModel):
    document_id: str
    title: str
    key_points: list[str]
    summary: str


class VideoQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_video(url: str, output_dir: str) -> tuple[str, str]:
    """Download a video from a URL using yt-dlp and return (file_path, title).

    Falls back to a simple HTTP download for direct file URLs.
    """
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    is_youtube = host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")

    # Try yt-dlp first (handles YouTube, Vimeo, etc.)
    try:
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "3",
                "--no-simulate",
                "-o", output_template,
                "--print", "title",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            title = lines[0] if len(lines) >= 1 else "Untitled Video"
            # Find the downloaded audio file
            for file in Path(output_dir).iterdir():
                if file.suffix.lower() in {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".opus"}:
                    return str(file), title
            if is_youtube:
                raise RuntimeError("yt-dlp completed but did not produce a supported audio file")
            # If yt-dlp extracted with another extension
            for file in Path(output_dir).iterdir():
                if file.is_file() and file.suffix:
                    return str(file), title
        elif is_youtube:
            details = (result.stderr or result.stdout or "yt-dlp could not download this video").strip()
            raise RuntimeError(f"Could not download the YouTube video: {details[-800:]}")
    except FileNotFoundError:
        if is_youtube:
            raise RuntimeError("YouTube imports require yt-dlp; rebuild the API image with the current requirements")
        pass  # yt-dlp not installed, try direct download
    except subprocess.TimeoutExpired:
        raise RuntimeError("Video download timed out (10 minutes)")
    except RuntimeError:
        raise

    # Fallback: direct HTTP download for mp4/webm/mp3 URLs
    try:
        req = Request(url, headers={"User-Agent": "VoiceRAG/1.0"})
        with urlopen(req, timeout=300) as resp:
            content_type = resp.headers.get("Content-Type", "")
            ext = ".mp4"
            if "webm" in content_type:
                ext = ".webm"
            elif "mp3" in content_type or "mpeg" in content_type:
                ext = ".mp3"
            elif "wav" in content_type:
                ext = ".wav"
            filepath = os.path.join(output_dir, f"download{ext}")
            with open(filepath, "wb") as f:
                while chunk := resp.read(1024 * 1024):
                    f.write(chunk)
            
            # Derive title from URL if possible
            stem = Path(url.split("?")[0]).stem or "Imported Video"
            return filepath, stem
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Could not download video: {exc}") from exc


def _extract_audio(video_path: str, output_dir: str) -> str:
    """Extract audio from a video file using ffmpeg, returning the audio file path.
    
    If ffmpeg is not available, falls back to the native video file if supported by transcriber.
    """
    suffix = Path(video_path).suffix.lower()
    if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}:
        return video_path

    audio_path = os.path.join(output_dir, "extracted_audio.mp3")

    try:
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vn",  # No video
                "-acodec", "libmp3lame",
                "-ab", "128k",
                "-ar", "16000",
                "-y",  # Overwrite
                audio_path,
            ],
            capture_output=True,
            timeout=600,
            check=True,
        )
        if os.path.exists(audio_path):
            return audio_path
    except FileNotFoundError:
        # ffmpeg not installed: AssemblyAI accepts mp4, webm, mov directly
        if suffix in {".mp4", ".webm", ".mov", ".mkv", ".m4a"}:
            return video_path
        raise RuntimeError("ffmpeg is not installed; cannot convert video format")
    except subprocess.CalledProcessError as exc:
        # If ffmpeg failed on this file, check if AssemblyAI supports it directly
        if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
            return video_path
        raise RuntimeError(f"ffmpeg audio extraction failed: {exc.stderr.decode(errors='replace')[:500]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Audio extraction timed out")

    return video_path


def _extract_heuristic_points(text: str, title: str) -> dict:
    """Heuristic summary and key points extraction when LLM gateway is not available."""
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return {
            "key_points": ["No transcription content found."],
            "summary": "Transcript is empty or could not be processed.",
        }

    # Split into sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if len(s.strip()) > 25]
    if not sentences:
        return {
            "key_points": [clean_text[:200]],
            "summary": clean_text[:300],
        }

    # Pick 5-8 informative sentences spread across the transcript
    total = len(sentences)
    step = max(1, total // 7)
    selected_indices = list(range(0, total, step))[:7]
    key_points = [sentences[idx] for idx in selected_indices if idx < total]

    # Create a 2-sentence summary from early and concluding sentences
    summary_parts = [sentences[0]]
    if total > 2:
        summary_parts.append(sentences[-1])
    summary = " ".join(summary_parts)

    return {
        "key_points": key_points,
        "summary": summary,
    }


def _generate_key_points(text: str, title: str) -> dict:
    """Use the LLM gateway to extract key points and a summary from transcript text.
    
    Falls back gracefully to heuristic extraction if the LLM gateway is unreachable or unconfigured.
    """
    if not settings.assemblyai_api_key or not text.strip():
        return _extract_heuristic_points(text, title)

    # Truncate very long transcripts to fit context window
    max_chars = 30_000
    truncated = text[:max_chars] + ("..." if len(text) > max_chars else "")

    payload = {
        "model": settings.llm_gateway_model,
        "temperature": 0.2,
        "max_tokens": 1200,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert video and lecture analyst. Given a transcript of a video, "
                    "extract the most important points and provide an executive summary. "
                    "Respond ONLY with valid JSON having exactly two keys:\n"
                    '- "key_points": an array of 5 to 10 strings, each representing a clear, valuable insight or key concept from the video.\n'
                    '- "summary": a comprehensive 2-3 sentence overview explaining what the video covers and its main takeaway.\n'
                    "Do NOT output markdown fences, backticks, or any additional explanation. Output raw JSON only."
                ),
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nTranscript:\n{truncated}",
            },
        ],
    }

    request = Request(
        settings.llm_gateway_url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": settings.assemblyai_api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode())
        
        answer_text = result["choices"][0]["message"]["content"].strip()
        answer_text = re.sub(r"^```(?:json)?\s*", "", answer_text)
        answer_text = re.sub(r"\s*```$", "", answer_text)
        parsed = json.loads(answer_text)
        return {
            "key_points": parsed.get("key_points") or _extract_heuristic_points(text, title)["key_points"],
            "summary": parsed.get("summary") or _extract_heuristic_points(text, title)["summary"],
        }
    except Exception:
    # Fallback to heuristic extraction
        return _extract_heuristic_points(text, title)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/video/import")
async def import_video_url(
    request: FastAPIRequest,
    body: VideoURLRequest,
    user: Annotated[User | None, Depends(get_current_user)],
):
    """Import a video from a URL (YouTube, Vimeo, direct link):
    download → extract audio → transcribe → vector index → generate key points.
    """
    tmpdir = tempfile.mkdtemp(prefix="voicerag-video-")
    try:
        # 1. Download video
        video_path, auto_title = await asyncio.to_thread(_download_video, body.url, tmpdir)
        doc_title = (body.title or auto_title or "Imported Video").strip()

        # 2. Extract audio from video
        audio_path = await asyncio.to_thread(_extract_audio, video_path, tmpdir)

        # 3. Copy audio to upload directory
        document_id = str(uuid.uuid4())
        suffix = Path(audio_path).suffix or ".mp3"
        destination = Path(request.app.state.settings.upload_dir) / f"{document_id}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(shutil.copy2, audio_path, str(destination))

        # 4. Create document record
        document = Document(
            id=document_id,
            owner_id=user.id if user else None,
            title=doc_title,
            filename=f"{doc_title[:80]}{suffix}",
            storage_path=str(destination),
            status=DocumentStatus.processing,
        )
        async with request.app.state.session_factory() as session:
            session.add(document)
            await session.commit()

        # 5. Transcribe
        try:
            transcript = await asyncio.to_thread(
                request.app.state.transcriber.transcribe, str(destination)
            )
            raw = getattr(transcript, "json_response", {}) or {}
            text = transcript.text or ""
            metadata = {
                "document_id": document_id,
                "title": doc_title,
                "assemblyai_transcript_id": getattr(transcript, "id", None),
                "source_url": body.url,
            }
            if user:
                metadata["owner_id"] = user.id

            words = [
                {
                    "text": getattr(w, "text", None),
                    "start": getattr(w, "start", None),
                    "end": getattr(w, "end", None),
                }
                for w in (getattr(transcript, "words", None) or [])
            ]

            # 6. Index in vector store
            try:
                await asyncio.to_thread(
                    request.app.state.pipeline.add_document, text, metadata, words
                )
            except TypeError:
                await asyncio.to_thread(
                    request.app.state.pipeline.add_document, text, metadata
                )

            # 7. Generate key points and summary
            key_points_data = await asyncio.to_thread(
                _generate_key_points, text, doc_title
            )

            # 8. Save transcript and update status
            async with request.app.state.session_factory() as session:
                saved = await session.get(Document, document_id)
                saved.status = DocumentStatus.completed
                session.add(
                    Transcript(
                        document_id=document_id,
                        assemblyai_id=getattr(transcript, "id", None),
                        text=text,
                        words_json=json.dumps(words),
                        language_code=raw.get("language_code"),
                        speech_model=raw.get("speech_model_used"),
                    )
                )
                await session.commit()

            return {
                "id": document_id,
                "title": doc_title,
                "status": "completed",
                "key_points": key_points_data["key_points"],
                "summary": key_points_data["summary"],
                "transcript_preview": text[:500] + ("..." if len(text) > 500 else ""),
            }

        except Exception as exc:
            async with request.app.state.session_factory() as session:
                saved = await session.get(Document, document_id)
                if saved:
                    saved.status = DocumentStatus.failed
                    saved.error = str(exc)[:2000]
                    await session.commit()
            raise HTTPException(status_code=502, detail=f"Processing failed: {exc}") from exc

    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video import failed: {exc}") from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/video/upload")
async def upload_video_file(
    request: FastAPIRequest,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str | None, Form()] = None,
    user: Annotated[User | None, Depends(get_current_user)] = None,
):
    """Directly upload a video file (.mp4, .webm, .mov, .mkv, .avi, etc.):
    save → extract audio if needed → transcribe → vector index → generate key points.
    """
    filename = Path(file.filename or "video.mp4").name
    raw_suffix = Path(filename).suffix.lower()
    allowed = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
    if raw_suffix not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported format {raw_suffix}. Please upload a video or audio file.")

    doc_title = (title or Path(filename).stem).strip()
    if not doc_title:
        doc_title = "Uploaded Video"

    tmpdir = tempfile.mkdtemp(prefix="voicerag-upload-")
    try:
        temp_input = os.path.join(tmpdir, filename)
        with open(temp_input, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        # Extract audio or keep video
        audio_path = await asyncio.to_thread(_extract_audio, temp_input, tmpdir)

        document_id = str(uuid.uuid4())
        suffix = Path(audio_path).suffix or ".mp3"
        destination = Path(request.app.state.settings.upload_dir) / f"{document_id}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(shutil.copy2, audio_path, str(destination))

        # Create Document record
        document = Document(
            id=document_id,
            owner_id=user.id if user else None,
            title=doc_title,
            filename=filename,
            storage_path=str(destination),
            status=DocumentStatus.processing,
        )
        async with request.app.state.session_factory() as session:
            session.add(document)
            await session.commit()

        # Transcribe & index
        try:
            transcript = await asyncio.to_thread(
                request.app.state.transcriber.transcribe, str(destination)
            )
            raw = getattr(transcript, "json_response", {}) or {}
            text = transcript.text or ""
            metadata = {
                "document_id": document_id,
                "title": doc_title,
                "assemblyai_transcript_id": getattr(transcript, "id", None),
                "filename": filename,
            }
            if user:
                metadata["owner_id"] = user.id

            words = [
                {
                    "text": getattr(w, "text", None),
                    "start": getattr(w, "start", None),
                    "end": getattr(w, "end", None),
                }
                for w in (getattr(transcript, "words", None) or [])
            ]

            try:
                await asyncio.to_thread(
                    request.app.state.pipeline.add_document, text, metadata, words
                )
            except TypeError:
                await asyncio.to_thread(
                    request.app.state.pipeline.add_document, text, metadata
                )

            key_points_data = await asyncio.to_thread(
                _generate_key_points, text, doc_title
            )

            async with request.app.state.session_factory() as session:
                saved = await session.get(Document, document_id)
                saved.status = DocumentStatus.completed
                session.add(
                    Transcript(
                        document_id=document_id,
                        assemblyai_id=getattr(transcript, "id", None),
                        text=text,
                        words_json=json.dumps(words),
                        language_code=raw.get("language_code"),
                        speech_model=raw.get("speech_model_used"),
                    )
                )
                await session.commit()

            return {
                "id": document_id,
                "title": doc_title,
                "status": "completed",
                "key_points": key_points_data["key_points"],
                "summary": key_points_data["summary"],
                "transcript_preview": text[:500] + ("..." if len(text) > 500 else ""),
            }
        except Exception as exc:
            async with request.app.state.session_factory() as session:
                saved = await session.get(Document, document_id)
                if saved:
                    saved.status = DocumentStatus.failed
                    saved.error = str(exc)[:2000]
                    await session.commit()
            raise HTTPException(status_code=502, detail=f"Processing failed: {exc}") from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        await file.close()


@router.get("/documents/{document_id}/key-points", response_model=KeyPointsResponse)
@router.post("/documents/{document_id}/key-points", response_model=KeyPointsResponse)
async def get_key_points(
    request: FastAPIRequest,
    document_id: str,
    user: Annotated[User | None, Depends(get_current_user)],
):
    """Generate or retrieve key points and summary from an existing document's transcript."""
    async with request.app.state.session_factory() as session:
        document = await session.get(Document, document_id)
        if not document or (user and document.owner_id != user.id):
            raise HTTPException(status_code=404, detail="Document not found")
        if not document.transcript or not document.transcript.text:
            raise HTTPException(status_code=422, detail="Transcript is not ready yet")
        text = document.transcript.text
        title = document.title

    result = await asyncio.to_thread(_generate_key_points, text, title)

    return KeyPointsResponse(
        document_id=document_id,
        title=title,
        key_points=result["key_points"],
        summary=result["summary"],
    )


@router.post("/documents/{document_id}/ask")
async def ask_video_question(
    request: FastAPIRequest,
    document_id: str,
    body: VideoQuestionRequest,
    user: Annotated[User | None, Depends(get_current_user)],
):
    """Ask a question strictly grounded in this specific video.
    
    Returns grounded answers, citations with timestamps, and confidence scores so
    users never need to consult an external AI.
    """
    async with request.app.state.session_factory() as session:
        document = await session.get(Document, document_id)
        if not document or (user and document.owner_id != user.id):
            raise HTTPException(status_code=404, detail="Document not found")
        if not document.transcript:
            raise HTTPException(status_code=422, detail="Video transcript is not ready yet")

    raw_sources = request.app.state.pipeline.search(body.question, body.limit, document_id)
    raw_sources = [
        source
        for source in raw_sources
        if source.distance is None or source.distance <= request.app.state.settings.retrieval_max_distance
    ]
    if not raw_sources:
        return {
            "answer": "No relevant parts found in the video transcript for this question.",
            "grounded": False,
            "citations": [],
            "confidence": 0.0,
            "sources": [],
        }

    try:
        owner_id = user.id if user else None
        res = await asyncio.to_thread(
            request.app.state.answer_engine.answer,
            body.question,
            body.limit,
            document_id,
            owner_id,
        )
        if res.get("answer") and res.get("answer") != "I couldn't find that in the indexed transcripts.":
            return res
    except Exception:
        pass

    # High-quality extractive grounding from the retrieved video transcript chunks
    sources_data = [
        {
            "citation": f"S{i+1}",
            "text": s.text,
            "metadata": s.metadata,
        }
        for i, s in enumerate(raw_sources)
    ]
    best_chunk = raw_sources[0]
    meta = best_chunk.metadata or {}
    start_sec = (meta.get("start_ms") or 0) / 1000
    timestamp_str = f"{int(start_sec // 60):02d}:{int(start_sec % 60):02d}" if "start_ms" in meta else ""
    ts_prefix = f"[{timestamp_str}] " if timestamp_str else ""
    
    return {
        "answer": f"Based on the lecture transcript [S1]: {ts_prefix}{best_chunk.text}",
        "answer_mode": "transcript_excerpt",
        "grounded": True,
        "citations": ["S1"],
        "confidence": round(max(0.0, min(1.0, 1.0 - (best_chunk.distance or 0.0))), 3),
        "sources": sources_data,
    }
