import logging
import uuid

from src.db.repositories.documents import (
    delete_document as repo_delete_document,
    delete_document_chunks as repo_delete_document_chunks,
    get_chunk_by_chunk_id,
    get_document_by_folder_and_storage_path,
    get_document_by_id,
    get_document_by_sharepoint_item_id,
    get_document_chunks,
    get_document_reference as repo_get_document_reference,
    insert_document,
    list_chunk_ids,
    list_documents,
    list_documents_by_storage_paths,
    list_documents_with_sharepoint_ids,
    update_document,
)
from src.services.document_processing_service import (
    document_summary_vector_id,
    delete_document_vectors,
    index_document_summary,
    split_document,
    store_document_chunks,
)
from src.services.folder_service import get_folder
from src.services.rewriter import rewrite_path_to_summary
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def _cleanup_document_index(document_id: str) -> None:
    """Remove vector rows and chunk rows; keep the documents row."""
    chunk_ids = list_chunk_ids(document_id)

    try:
        delete_document_vectors([document_summary_vector_id(document_id)])
    except Exception as vector_error:
        logger.warning(f"Failed to delete document summary vector: {vector_error}")

    if chunk_ids:
        try:
            delete_document_vectors(chunk_ids)
        except Exception as vector_error:
            logger.warning(f"Failed to delete chunk vectors: {vector_error}")

    repo_delete_document_chunks(document_id)


def _find_document_in_folder(folder_id: int, storage_path: str) -> dict | None:
    return get_document_by_folder_and_storage_path(folder_id, storage_path)


def rollback_document(document_id: str) -> None:
    """
    Remove document_chunks rows, vector rows, and the documents row.
    Used when indexing fails and we need to undo the DB insert.
    """
    doc_response = get_document_by_id(document_id)
    if not doc_response:
        logger.warning(f"Rollback skipped: document {document_id} not found")
        return

    chunk_ids = list_chunk_ids(document_id)

    try:
        delete_document_vectors([document_summary_vector_id(document_id)])
    except Exception as vector_error:
        logger.warning(f"Rollback: failed to delete document summary vector: {vector_error}")

    if chunk_ids:
        try:
            delete_document_vectors(chunk_ids)
        except Exception as vector_error:
            logger.warning(f"Rollback: failed to delete chunk vectors: {vector_error}")

    repo_delete_document_chunks(document_id)
    repo_delete_document(document_id)
    logger.info(f"Rolled back document {document_id} from PostgreSQL")


def index_docs_summary(
    document_id: str,
    file_path: str,
    title: str = "",
    is_image_doc: bool = False,
) -> None:
    """Generate a path-based summary and index it for document routing."""
    summary = rewrite_path_to_summary(file_path)
    index_document_summary(
        document_id=document_id,
        summary=summary,
        storage_path=file_path,
        title=title,
        is_image_doc=is_image_doc,
    )


def get_documents_by_storage_paths(storage_paths: list[str]) -> list[dict]:
    return list_documents_by_storage_paths(storage_paths)


def get_scanned_storage_paths(storage_paths: list[str]) -> list[str]:
    docs = get_documents_by_storage_paths(storage_paths)
    scanned_paths: list[str] = []
    for doc in docs:
        path = doc.get("storage_path")
        if not path:
            continue
        if doc.get("is_image_pdf"):
            scanned_paths.append(path)
    return scanned_paths


def index_docs(document_id: str) -> None:
    """
    Indexes a document into Pinecone.
    Text PDFs: summary vector + content chunks.
    Scanned/image PDFs: summary vector only (no chunking).
    Word docs: summary vector + content chunks (never scanned).
    Raises on failure so callers can roll back.
    """
    doc_data = get_document_by_id(document_id)
    if not doc_data:
        raise Exception(f"Document with ID {document_id} not found")

    storage_path = doc_data.get("storage_path")
    file_url = doc_data.get("file_url")
    source_type = doc_data.get("source_type", "pdf")
    if not storage_path:
        raise Exception(f"Document {document_id} has no storage_path")
    if not file_url:
        raise Exception(f"Document {document_id} has no file_url")

    # Only PDFs can be scanned; Word docs are always text-based
    is_image_pdf = False
    if source_type == "pdf":
        if ".drawio.pdf" in storage_path.lower():
            is_image_pdf = True
        else:
            from src.services.image_document_service import is_scanned_pdf

            is_image_pdf = is_scanned_pdf(file_url)

    update_document(document_id, {"is_image_pdf": is_image_pdf})

    index_docs_summary(
        document_id=document_id,
        file_path=storage_path,
        title=doc_data.get("title", ""),
        is_image_doc=is_image_pdf,
    )

    if is_image_pdf:
        logger.info(
            f"Document {document_id} is a scanned PDF; indexed summary only (no chunks)"
        )
        return

    chunks = split_document(document_id)
    store_document_chunks(chunks)
    logger.info(f"Document {document_id} indexed successfully ({len(chunks)} chunks)")


def get_all_documents(folder_id: int | None = None):
    """
    Retrieves documents, optionally filtered by folder.
    """
    try:
        data = list_documents(folder_id)
        return {
            "status": "success",
            "data": data,
        }
    except Exception as e:
        logger.error(f"Error fetching documents: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
        }


def _is_valid_chunk_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_document_reference_id(reference: str) -> str | None:
    """Scanned PDF citations use doc-{id} or a bare numeric document id."""
    if reference.startswith("doc-"):
        document_id = reference.removeprefix("doc-")
        return document_id if document_id.isdigit() else None
    if reference.isdigit():
        return reference
    return None


def get_document_reference(document_id: str):
    """
    Return reference info for a whole document (used by scanned PDF citations).
    """
    try:
        doc = repo_get_document_reference(int(document_id))
        if not doc:
            return {"status": "error", "message": "Document not found"}

        title = doc.get("title") or "Unknown Document"
        if doc.get("is_image_pdf"):
            content = (
                f"Tài liệu quét PDF: {title}\n\n"
                "Đây là tài liệu scan (hình ảnh), không có đoạn văn bản chunk. "
                "Mở file PDF gốc để xem toàn bộ nội dung."
            )
        else:
            content = f"Tài liệu: {title}"

        return {
            "status": "success",
            "data": {
                "content": content,
                "metadata": {
                    "title": title,
                    "file_url": doc.get("file_url"),
                    "is_image_pdf": bool(doc.get("is_image_pdf")),
                    "document_id": doc.get("id"),
                },
            },
        }
    except Exception as e:
        logger.error(f"Error fetching document reference: {str(e)}")
        return {"status": "error", "message": str(e)}


def get_chunk(chunk_id: str):
    """
    Retrieves a text chunk by UUID, or a whole-document reference for scanned PDFs.
    """
    document_id = _parse_document_reference_id(chunk_id)
    if document_id:
        return get_document_reference(document_id)

    if not _is_valid_chunk_uuid(chunk_id):
        return {"status": "error", "message": "Invalid chunk id"}

    try:
        chunk_data = get_chunk_by_chunk_id(chunk_id)
        if not chunk_data:
            return {"status": "error", "message": "Chunk not found"}

        formatted_data = {
            "content": chunk_data.get("content"),
            "metadata": {
                "title": chunk_data.get("title") or "Unknown Document",
                "file_url": chunk_data.get("file_url"),
                "document_id": chunk_data.get("document_id"),
            },
        }

        return {"status": "success", "data": formatted_data}
    except Exception as e:
        logger.error(f"Error fetching chunk: {str(e)}")
        return {"status": "error", "message": str(e)}


def delete_document(document_id: str):
    """
    Deletes a document: vector rows, chunk rows, and the documents row.
    No storage file cleanup needed — files live in SharePoint.
    """
    try:
        doc_response = get_document_by_id(document_id)
        chunk_ids = list_chunk_ids(document_id)

        if not doc_response:
            return {"status": "error", "message": "Document not found"}

        try:
            delete_document_vectors([document_summary_vector_id(document_id)])
        except Exception as vector_error:
            logger.warning(
                f"Failed to delete document summary vector: {str(vector_error)}"
            )

        if chunk_ids:
            try:
                logger.info(f"Deleting {len(chunk_ids)} chunk vectors")
                delete_document_vectors(chunk_ids)
            except Exception as vector_error:
                logger.warning(f"Failed to delete chunk vectors: {str(vector_error)}")

        repo_delete_document_chunks(document_id)

        logger.info(f"Deleting document metadata for ID: {document_id}")
        repo_delete_document(document_id)

        return {
            "status": "success",
            "message": "Document deleted successfully",
        }
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
        }


# ---------------------------------------------------------------------------
# Sync helpers — used by sharepoint_sync_service
# ---------------------------------------------------------------------------

def _timestamps_equal(t1_str: str, t2_str: str) -> bool:
    """Compare two ISO timestamp strings by parsing them to datetime objects."""
    if not t1_str or not t2_str:
        return False
    from datetime import datetime

    try:
        # Standardize Z suffix to +00:00
        s1 = t1_str.replace("Z", "+00:00")
        s2 = t2_str.replace("Z", "+00:00")
        dt1 = datetime.fromisoformat(s1)
        dt2 = datetime.fromisoformat(s2)
        return dt1 == dt2
    except Exception:
        return t1_str == t2_str


def upsert_document_for_sync(
    title: str,
    file_url: str,
    storage_path: str,
    folder_id: int,
    source_type: str,
    sharepoint_item_id: str,
    sharepoint_modified_at: str,
) -> dict:
    """
    Insert or update a document row for SharePoint sync.
    Returns {"document_id": ..., "is_new": bool, "needs_reindex": bool}.
    """
    existing = get_document_by_sharepoint_item_id(sharepoint_item_id)

    if existing:
        old_modified = existing.get("sharepoint_modified_at") or ""
        if _timestamps_equal(old_modified, sharepoint_modified_at):
            return {
                "document_id": str(existing["id"]),
                "is_new": False,
                "needs_reindex": False,
            }

        _cleanup_document_index(str(existing["id"]))
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
    document_id = str(row["id"])
    logger.info(f"Inserted new document {document_id} for sync: {storage_path}")
    return {"document_id": document_id, "is_new": True, "needs_reindex": True}


if __name__ == "__main__":
    print(
        get_scanned_storage_paths(
            [
                "1. STDC & MTCV các phòng ban/1. Khối F&B/L'amuse + YGS/20240601_Nhân viên thu ngân - pha chế - phục vụ.pdf"
            ]
        )
    )
