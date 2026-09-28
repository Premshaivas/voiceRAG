from __future__ import annotations

import uuid
from typing import Any


class QdrantCollection:
    def __init__(self, client: Any, collection_name: str, vector_size: int):
        from qdrant_client.models import Distance, VectorParams
        self.client = client
        self.collection_name = collection_name
        if not client.collection_exists(collection_name):
            client.create_collection(collection_name=collection_name, vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE))

    @staticmethod
    def _point_id(value: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))

    @staticmethod
    def _filter(where: dict[str, Any] | None):
        if not where:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        if "$and" in where:
            conditions = [QdrantCollection._filter(item) for item in where["$and"]]
            return Filter(must=[condition.must[0] for condition in conditions if condition and condition.must])
        must = [FieldCondition(key=key, match=MatchValue(value=value)) for key, value in where.items()]
        return Filter(must=must)

    def upsert(self, ids, documents, embeddings, metadatas):
        from qdrant_client.models import PointStruct
        points = []
        for original_id, text, vector, metadata in zip(ids, documents, embeddings, metadatas):
            payload = {**metadata, "_text": text, "_original_id": original_id}
            points.append(PointStruct(id=self._point_id(original_id), vector=vector, payload=payload))
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def delete(self, where):
        from qdrant_client.models import FilterSelector
        self.client.delete(collection_name=self.collection_name, points_selector=FilterSelector(filter=self._filter(where)), wait=True)

    def query(self, query_embeddings, n_results, include, where=None):
        response = self.client.query_points(collection_name=self.collection_name, query=query_embeddings[0], limit=n_results, query_filter=self._filter(where), with_payload=True, with_vectors=False)
        points = response.points
        return {"ids": [[point.payload.get("_original_id", str(point.id)) for point in points]], "documents": [[point.payload.get("_text", "") for point in points]], "metadatas": [[{key: value for key, value in point.payload.items() if not key.startswith("_")} for point in points]], "distances": [[float(1 - point.score) if point.score is not None else None for point in points]]}
