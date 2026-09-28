from __future__ import annotations

import hashlib
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from .cache import TTLCache
from .config import settings


@dataclass(frozen=True)
class SearchResult:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None


class RAGPipeline:
    def __init__(self, persist_directory: str | None = None, embedding_model: str = "all-MiniLM-L6-v2", chunk_size: int = 900, chunk_overlap: int = 150, client: Any = None, embedder: Any = None):
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and overlap must be below chunk_size")
        self.chunk_size, self.chunk_overlap = chunk_size, chunk_overlap
        self._lock = threading.RLock()
        if embedder is None:
            from sentence_transformers import SentenceTransformer
            embedder = SentenceTransformer(embedding_model)
        self.embedder = embedder
        if client is not None:
            self.client = client
            self.collection = client.get_or_create_collection(name="voice_transcripts", metadata={"hnsw:space": "cosine"})
        elif settings.vector_backend.lower() == "qdrant":
            from qdrant_client import QdrantClient
            from .qdrant_storage import QdrantCollection
            qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
            vector_size = embedder.get_sentence_embedding_dimension() if hasattr(embedder, "get_sentence_embedding_dimension") else len(embedder.encode(["health"], show_progress_bar=False, normalize_embeddings=True)[0])
            self.client = qdrant
            self.collection = QdrantCollection(qdrant, settings.qdrant_collection, vector_size)
        else:
            import chromadb
            self.client = chromadb.PersistentClient(path=persist_directory or settings.chroma_dir)
            self.collection = self.client.get_or_create_collection(name="voice_transcripts", metadata={"hnsw:space": "cosine"})
        self._embedding_cache: TTLCache[Any] = TTLCache(settings.query_embedding_cache_max_entries, 3600)

    def _encode(self, texts: list[str]):
        encoded: list[Any] = []
        missing: list[str] = []
        missing_indices: list[int] = []
        for index, text in enumerate(texts):
            cached = self._embedding_cache.get(text)
            if cached is None:
                encoded.append(None)
                missing.append(text)
                missing_indices.append(index)
            else:
                encoded.append(cached)
        if missing:
            result = self.embedder.encode(missing, show_progress_bar=False, normalize_embeddings=True)
            fresh = result.tolist() if hasattr(result, "tolist") else result
            for index, vector, text in zip(missing_indices, fresh, missing):
                encoded[index] = vector
                self._embedding_cache.set(text, vector)
        return encoded

    def add_document(self, text: str, metadata: dict[str, Any] | None = None, words: list[Any] | None = None) -> list[str]:
        normalized = self._normalize_text(text)
        if not normalized:
            raise ValueError("Cannot index an empty transcript")
        base = self._sanitize_metadata(metadata or {})
        document_id = str(base.get("document_id") or base.get("assemblyai_transcript_id") or uuid.uuid4())
        timestamped = self._timestamped_chunks(words or [])
        if timestamped:
            chunks = [item[0] for item in timestamped]
            timing = [(item[1], item[2]) for item in timestamped]
        else:
            chunks = self._chunk_text(normalized)
            timing = [(None, None)] * len(chunks)
        ids = [self._chunk_id(document_id, i, chunk) for i, chunk in enumerate(chunks)]
        embeddings = self._encode(chunks)
        metadatas = []
        for i, chunk in enumerate(chunks):
            start_ms, end_ms = timing[i]
            item = {**base, "document_id": document_id, "chunk_index": i, "chunk_count": len(chunks)}
            if start_ms is not None:
                item["start_ms"], item["end_ms"] = start_ms, end_ms
            metadatas.append(item)
        with self._lock:
            self.collection.delete(where={"document_id": document_id})
            self.collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        return ids

    index_document = add_document

    def search(self, query: str, limit: int = 5, document_id: str | None = None, owner_id: str | None = None) -> list[SearchResult]:
        query = self._normalize_text(query)
        if not query:
            raise ValueError("Search query cannot be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        where: dict[str, Any] | None = None
        if document_id and owner_id:
            where = {"$and": [{"document_id": document_id}, {"owner_id": owner_id}]}
        elif document_id:
            where = {"document_id": document_id}
        elif owner_id:
            where = {"owner_id": owner_id}
        args: dict[str, Any] = {"query_embeddings": self._encode([query]), "n_results": limit, "include": ["documents", "metadatas", "distances"]}
        if where:
            args["where"] = where
        with self._lock:
            response = self.collection.query(**args)
        ids = (response.get("ids") or [[]])[0]
        docs = (response.get("documents") or [[]])[0]
        metas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        return [SearchResult(ids[i], docs[i] or "", metas[i] or {}, float(distances[i]) if i < len(distances) and distances[i] is not None else None) for i in range(len(ids))]

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self.collection.delete(where={"document_id": document_id})

    def _chunk_text(self, text: str) -> list[str]:
        chunks, start = [], 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if end < len(text):
                boundary = max(text.rfind(mark, start + self.chunk_size // 2, end) for mark in (". ", "? ", "! ", "\n", " "))
                if boundary > start:
                    end = boundary + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    def _timestamped_chunks(self, words: list[Any]) -> list[tuple[str, int, int]]:
        normalized_words: list[tuple[str, int, int]] = []
        for word in words:
            text = word.get("text") if isinstance(word, dict) else getattr(word, "text", None)
            start = word.get("start") if isinstance(word, dict) else getattr(word, "start", None)
            end = word.get("end") if isinstance(word, dict) else getattr(word, "end", None)
            if text and start is not None and end is not None:
                normalized_words.append((str(text).strip(), int(start), int(end)))
        if not normalized_words:
            return []
        chunks: list[tuple[str, int, int]] = []
        current: list[tuple[str, int, int]] = []
        current_length = 0
        overlap_words = max(1, self.chunk_overlap // 8)
        for word in normalized_words:
            extra = len(word[0]) + (1 if current else 0)
            if current and current_length + extra > self.chunk_size:
                chunks.append((" ".join(item[0] for item in current), current[0][1], current[-1][2]))
                current = current[-overlap_words:]
                current_length = sum(len(item[0]) + 1 for item in current)
            current.append(word)
            current_length += extra
        if current:
            chunks.append((" ".join(item[0] for item in current), current[0][1], current[-1][2]))
        return chunks

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _chunk_id(document_id: str, index: int, text: str) -> str:
        return f"{document_id}:{index}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return {str(k): (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in metadata.items() if v is not None}
