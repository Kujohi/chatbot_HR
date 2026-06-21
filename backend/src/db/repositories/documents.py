from typing import Iterable

from psycopg2.extras import execute_values

from src.db.postgres import (
    bulk_insert_rows,
    delete_where,
    execute,
    fetch_all,
    fetch_one,
    get_cursor,
    insert_row,
    update_row,
)


def get_document_by_id(document_id: str | int) -> dict | None:
    return fetch_one(
        """
        SELECT id, title, source_type, file_url, storage_path, folder_id, owner_id,
               status, is_image_pdf, sharepoint_item_id, sharepoint_modified_at,
               created_at, updated_at
        FROM documents
        WHERE id = %s
        """,
        (document_id,),
    )


def get_document_by_sharepoint_item_id(sharepoint_item_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, sharepoint_modified_at
        FROM documents
        WHERE sharepoint_item_id = %s
        LIMIT 1
        """,
        (sharepoint_item_id,),
    )


def get_document_by_folder_and_storage_path(folder_id: int, storage_path: str) -> dict | None:
    return fetch_one(
        """
        SELECT *
        FROM documents
        WHERE folder_id = %s AND storage_path = %s
        LIMIT 1
        """,
        (folder_id, storage_path),
    )


def list_documents(folder_id: int | None = None) -> list[dict]:
    if folder_id is None:
        rows = fetch_all(
            """
            SELECT d.*, f.id AS folder_ref_id, f.name AS folder_ref_name, f.slug AS folder_ref_slug
            FROM documents d
            LEFT JOIN document_folders f ON f.id = d.folder_id
            ORDER BY d.created_at DESC
            """
        )
    else:
        rows = fetch_all(
            """
            SELECT d.*, f.id AS folder_ref_id, f.name AS folder_ref_name, f.slug AS folder_ref_slug
            FROM documents d
            LEFT JOIN document_folders f ON f.id = d.folder_id
            WHERE d.folder_id = %s
            ORDER BY d.created_at DESC
            """,
            (folder_id,),
        )

    for row in rows:
        folder_id_value = row.pop("folder_ref_id", None)
        folder_name = row.pop("folder_ref_name", None)
        folder_slug = row.pop("folder_ref_slug", None)
        row["document_folders"] = (
            {
                "id": folder_id_value,
                "name": folder_name,
                "slug": folder_slug,
            }
            if folder_id_value is not None
            else None
        )
    return rows


def list_documents_by_storage_paths(storage_paths: list[str]) -> list[dict]:
    if not storage_paths:
        return []
    return fetch_all(
        """
        SELECT id, title, file_url, storage_path, is_image_pdf, sharepoint_item_id
        FROM documents
        WHERE storage_path = ANY(%s)
        """,
        (storage_paths,),
    )


def list_documents_with_sharepoint_ids() -> list[dict]:
    return fetch_all(
        """
        SELECT id, sharepoint_item_id, storage_path
        FROM documents
        WHERE sharepoint_item_id IS NOT NULL
        """
    )


def list_all_document_folder_links() -> list[dict]:
    return fetch_all(
        """
        SELECT id, folder_id
        FROM documents
        """
    )


def list_chunk_ids(document_id: str | int) -> list[str]:
    rows = fetch_all(
        """
        SELECT chunk_id
        FROM document_chunks
        WHERE document_id = %s
        """,
        (document_id,),
    )
    return [str(row["chunk_id"]) for row in rows if row.get("chunk_id")]


def delete_document_chunks(document_id: str | int) -> None:
    delete_where("document_chunks", "document_id = %s", (document_id,))


def delete_document(document_id: str | int) -> None:
    delete_where("documents", "id = %s", (document_id,))


def update_document(document_id: str | int, fields: dict) -> dict | None:
    if not fields:
        return get_document_by_id(document_id)
    return update_row("documents", fields, "id = %s", (document_id,), returning="*")


def insert_document(document_data: dict) -> dict:
    row = insert_row("documents", document_data, returning="*")
    if row is None:
        raise RuntimeError("Failed to insert document")
    return row


def insert_document_chunks(chunks: list[dict]) -> None:
    if not chunks:
        return
    with get_cursor(commit=True) as cursor:
        execute_values(
            cursor,
            """
            INSERT INTO document_chunks (document_id, chunk_id, content)
            VALUES %s
            """,
            [
                (
                    chunk["document_id"],
                    chunk["chunk_id"],
                    chunk["content"],
                )
                for chunk in chunks
            ],
        )


def get_document_reference(document_id: str | int) -> dict | None:
    return fetch_one(
        """
        SELECT id, title, file_url, is_image_pdf
        FROM documents
        WHERE id = %s
        """,
        (document_id,),
    )


def get_chunk_by_chunk_id(chunk_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT c.id AS chunk_row_id,
               c.document_id,
               c.chunk_id,
               c.content,
               c.created_at AS chunk_created_at,
               d.title,
               d.file_url
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.chunk_id = %s
        """,
        (chunk_id,),
    )


def get_document_chunks(document_id: str | int) -> list[dict]:
    return fetch_all(
        """
        SELECT chunk_id
        FROM document_chunks
        WHERE document_id = %s
        """,
        (document_id,),
    )


def upsert_document_for_sync(
    title: str,
    file_url: str,
    storage_path: str,
    folder_id: int,
    source_type: str,
    sharepoint_item_id: str,
    sharepoint_modified_at: str,
) -> dict:
    existing = get_document_by_sharepoint_item_id(sharepoint_item_id)
    if existing:
        old_modified = existing.get("sharepoint_modified_at") or ""
        if old_modified == sharepoint_modified_at:
            return {
                "document_id": str(existing["id"]),
                "is_new": False,
                "needs_reindex": False,
            }

        update_document(
            existing["id"],
            {
                "title": title,
                "file_url": file_url,
                "storage_path": storage_path,
                "folder_id": folder_id,
                "source_type": source_type,
                "sharepoint_modified_at": sharepoint_modified_at,
                "status": "uploaded",
                "is_image_pdf": False,
            },
        )
        return {
            "document_id": str(existing["id"]),
            "is_new": False,
            "needs_reindex": True,
        }

    document_data = {
        "title": title,
        "source_type": source_type,
        "file_url": file_url,
        "storage_path": storage_path,
        "folder_id": folder_id,
        "owner_id": "sharepoint_sync",
        "status": "uploaded",
        "sharepoint_item_id": sharepoint_item_id,
        "sharepoint_modified_at": sharepoint_modified_at,
    }
    row = insert_document(document_data)
    return {
        "document_id": str(row["id"]),
        "is_new": True,
        "needs_reindex": True,
    }
