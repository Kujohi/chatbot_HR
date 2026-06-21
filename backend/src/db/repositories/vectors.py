from __future__ import annotations

from typing import Any, Sequence

from psycopg2.extras import execute_values, Json
from pgvector.psycopg2.vector import Vector

from src.db.postgres import delete_where, fetch_all, get_cursor


def _normalize_embedding(embedding: Sequence[float] | None) -> list[float] | None:
    if embedding is None:
        return None
    return [float(value) for value in embedding]


def _to_vector(embedding: Sequence[float] | None) -> Vector | None:
    normalized = _normalize_embedding(embedding)
    if normalized is None:
        return None
    return Vector(normalized)


def upsert_document_vectors(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    values = []
    for row in rows:
        metadata = row.get("metadata") or {}
        values.append(
            (
                row["document_id"],
                row.get("chunk_id"),
                row["vector_key"],
                row["content"],
                Json(metadata),
                _to_vector(row.get("embedding")),
                bool(row.get("is_document", False)),
            )
        )

    query = """
        INSERT INTO document_chunks (
            document_id,
            chunk_id,
            vector_key,
            content,
            metadata,
            embedding,
            is_document
        )
        VALUES %s
        ON CONFLICT (vector_key) DO UPDATE SET
            document_id = EXCLUDED.document_id,
            chunk_id = EXCLUDED.chunk_id,
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            is_document = EXCLUDED.is_document,
            updated_at = CURRENT_TIMESTAMP
    """

    with get_cursor(commit=True) as cursor:
        execute_values(cursor, query, values)


def delete_vectors_by_keys(vector_keys: list[str]) -> None:
    if not vector_keys:
        return
    delete_where("document_chunks", "vector_key = ANY(%s)", (vector_keys,))


def delete_vectors_by_document_id(document_id: str | int) -> None:
    delete_where("document_chunks", "document_id = %s", (document_id,))


def search_vectors(
    query_embedding: Sequence[float],
    *,
    limit: int = 5,
    is_document: bool | None = None,
    storage_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    clauses = ["embedding IS NOT NULL"]
    params: list[Any] = []

    if is_document is not None:
        clauses.append("is_document = %s")
        params.append(is_document)

    if storage_paths:
        clauses.append("metadata->>'storage_path' = ANY(%s)")
        params.append(storage_paths)

    where_sql = " AND ".join(clauses)
    query = f"""
        SELECT
            id,
            document_id,
            chunk_id,
            vector_key,
            content,
            metadata,
            is_document,
            1 - (embedding <=> %s) AS similarity
        FROM document_chunks
        WHERE {where_sql}
        ORDER BY embedding <=> %s
        LIMIT %s
    """
    vector = _to_vector(query_embedding)
    params = [vector, *params, vector, limit]

    return fetch_all(query, params)
