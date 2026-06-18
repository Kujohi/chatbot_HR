from src.db.client import get_supabase
import logging
import uuid
from src.utils.utils import setup_logging
from src.services.document_processing_service import (
    split_document,
    store_document_chunks,
    pinecone_index,
    pinecone_delete,
    pinecone_index_document_summary,
    document_summary_vector_id,
)
from src.services.folder_service import get_folder
from src.services.rewriter import rewrite_path_to_summary

setup_logging()
logger = logging.getLogger(__name__)


def _cleanup_document_index(document_id: str) -> None:
    """Remove Pinecone vectors and chunk rows; keep the documents row."""
    supabase = get_supabase()
    chunk_response = (
        supabase.table("document_chunks")
        .select("chunk_id")
        .eq("document_id", document_id)
        .execute()
    )
    chunk_ids = [chunk["chunk_id"] for chunk in chunk_response.data if chunk.get("chunk_id")]

    try:
        pinecone_delete([document_summary_vector_id(document_id)])
    except Exception as pinecone_e:
        logger.warning(f"Failed to delete Pinecone document summary: {pinecone_e}")

    if chunk_ids:
        try:
            pinecone_delete(chunk_ids)
        except Exception as pinecone_e:
            logger.warning(f"Failed to delete Pinecone chunks: {pinecone_e}")

    supabase.table("document_chunks").delete().eq("document_id", document_id).execute()


def _find_document_in_folder(folder_id: int, storage_path: str) -> dict | None:
    supabase = get_supabase()
    response = (
        supabase.table("documents")
        .select("*")
        .eq("folder_id", folder_id)
        .eq("storage_path", storage_path)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]
    return None


def rollback_document(document_id: str) -> None:
    """
    Remove document_chunks rows, Pinecone vectors, and the documents row.
    Used when indexing fails and we need to undo the DB insert.
    """
    supabase = get_supabase()
    doc_response = supabase.table("documents").select("*").eq("id", document_id).execute()
    if not doc_response.data:
        logger.warning(f"Rollback skipped: document {document_id} not found")
        return

    chunk_response = (
        supabase.table("document_chunks")
        .select("chunk_id")
        .eq("document_id", document_id)
        .execute()
    )
    chunk_ids = [chunk["chunk_id"] for chunk in chunk_response.data if chunk.get("chunk_id")]

    try:
        pinecone_delete([document_summary_vector_id(document_id)])
    except Exception as pinecone_e:
        logger.warning(f"Rollback: failed to delete Pinecone document summary: {pinecone_e}")

    if chunk_ids:
        try:
            pinecone_delete(chunk_ids)
        except Exception as pinecone_e:
            logger.warning(f"Rollback: failed to delete Pinecone chunks: {pinecone_e}")

    supabase.table("document_chunks").delete().eq("document_id", document_id).execute()
    supabase.table("documents").delete().eq("id", document_id).execute()
    logger.info(f"Rolled back document {document_id} from Supabase")

def index_docs_summary(
    document_id: str,
    file_path: str,
    title: str = "",
    is_image_doc: bool = False,
) -> None:
    """Generate a path-based summary and index it in Pinecone for document routing."""
    summary = rewrite_path_to_summary(file_path)
    pinecone_index_document_summary(
        document_id=document_id,
        summary=summary,
        storage_path=file_path,
        title=title,
        is_image_doc=is_image_doc,
    )


def get_documents_by_storage_paths(storage_paths: list[str]) -> list[dict]:
    if not storage_paths:
        return []
    supabase = get_supabase()
    response = (
        supabase.table("documents")
        .select("id, title, file_url, storage_path, is_image_pdf, sharepoint_item_id")
        .in_("storage_path", storage_paths)
        .execute()
    )
    return response.data or []


def get_scanned_storage_paths(storage_paths: list[str]) -> list[str]:
    from src.services.image_document_service import is_scanned_pdf
    docs = get_documents_by_storage_paths(storage_paths)
    scanned_paths: list[str] = []
    for doc in docs:
        path = doc.get("storage_path")
        if not path:
            continue
        if doc.get("is_image_pdf"):
            scanned_paths.append(path)
            continue
        file_url = doc.get("file_url")
        if file_url and is_scanned_pdf(file_url):
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
    supabase = get_supabase()
    response = (
        supabase.table("documents")
        .select("storage_path, title, file_url, source_type")
        .eq("id", document_id)
        .execute()
    )
    if not response.data:
        raise Exception(f"Document with ID {document_id} not found")

    doc_data = response.data[0]
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
        from src.services.image_document_service import is_scanned_pdf
        is_image_pdf = is_scanned_pdf(file_url)

    supabase.table("documents").update({"is_image_pdf": is_image_pdf}).eq(
        "id", document_id
    ).execute()

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
    pinecone_index(chunks)
    logger.info(f"Document {document_id} indexed successfully ({len(chunks)} chunks)")


def get_all_documents(folder_id: int | None = None):
    """
    Retrieves documents, optionally filtered by folder.
    """
    try:
        supabase = get_supabase()
        query = supabase.table("documents").select(
            "*, document_folders(id, name, slug)"
        )
        if folder_id is not None:
            query = query.eq("folder_id", folder_id)
        response = query.order("created_at", desc=True).execute()
        return {
            "status": "success",
            "data": response.data
        }
    except Exception as e:
        logger.error(f"Error fetching documents: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
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
        supabase = get_supabase()
        response = (
            supabase.table("documents")
            .select("id, title, file_url, is_image_pdf")
            .eq("id", int(document_id))
            .execute()
        )
        if not response.data:
            return {"status": "error", "message": "Document not found"}

        doc = response.data[0]
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
        supabase = get_supabase()
        response = (
            supabase.table("document_chunks")
            .select("*, documents(title, file_url)")
            .eq("chunk_id", chunk_id)
            .execute()
        )
        if not response.data:
            return {"status": "error", "message": "Chunk not found"}

        chunk_data = response.data[0]
        doc_meta = chunk_data.get("documents") or {}
        formatted_data = {
            "content": chunk_data.get("content"),
            "metadata": {
                "title": doc_meta.get("title") or "Unknown Document",
                "file_url": doc_meta.get("file_url"),
                "document_id": chunk_data.get("document_id"),
            },
        }

        return {"status": "success", "data": formatted_data}
    except Exception as e:
        logger.error(f"Error fetching chunk: {str(e)}")
        return {"status": "error", "message": str(e)}

def delete_document(document_id: str):
    """
    Deletes a document: Pinecone vectors, chunk rows, and the documents row.
    No storage file cleanup needed — files live in SharePoint.
    """
    try:
        supabase = get_supabase()

        # 1. Get document metadata
        doc_response = supabase.table("documents").select("*").eq("id", document_id).execute()
        chunk_response = supabase.table("document_chunks").select("*").eq("document_id", document_id).execute()

        if not doc_response.data:
            return {"status": "error", "message": "Document not found"}

        # 2. Delete from pinecone index (document summary + chunks)
        try:
            pinecone_delete([document_summary_vector_id(document_id)])
        except Exception as pinecone_e:
            logger.warning(f"Failed to delete document summary from Pinecone: {str(pinecone_e)}")

        chunk_ids = [chunk.get("chunk_id") for chunk in chunk_response.data if chunk.get("chunk_id")]
        if chunk_ids:
            try:
                logger.info(f"Deleting {len(chunk_ids)} chunks from Pinecone")
                pinecone_delete(chunk_ids)
            except Exception as pinecone_e:
                logger.warning(f"Failed to delete chunks from Pinecone: {str(pinecone_e)}")

        # 3. Delete chunk rows from database
        supabase.table("document_chunks").delete().eq("document_id", document_id).execute()

        # 4. Delete document row from database
        logger.info(f"Deleting document metadata for ID: {document_id}")
        supabase.table("documents").delete().eq("id", document_id).execute()

        return {
            "status": "success",
            "message": "Document deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
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
    supabase = get_supabase()

    # Check if document already exists by sharepoint_item_id
    existing = (
        supabase.table("documents")
        .select("id, sharepoint_modified_at")
        .eq("sharepoint_item_id", sharepoint_item_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        doc = existing.data[0]
        old_modified = doc.get("sharepoint_modified_at") or ""
        if _timestamps_equal(old_modified, sharepoint_modified_at):
            # Unchanged — skip completely (no DB update)
            return {"document_id": str(doc["id"]), "is_new": False, "needs_reindex": False}

        # Modified — update metadata, caller will re-index
        _cleanup_document_index(str(doc["id"]))
        supabase.table("documents").update({
            "title": title,
            "file_url": file_url,
            "storage_path": storage_path,
            "folder_id": folder_id,
            "source_type": source_type,
            "sharepoint_modified_at": sharepoint_modified_at,
            "status": "uploaded",
            "is_image_pdf": False,
        }).eq("id", doc["id"]).execute()
        return {"document_id": str(doc["id"]), "is_new": False, "needs_reindex": True}

    # New document
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
    db_response = supabase.table("documents").insert(document_data).execute()
    if not db_response.data:
        raise Exception(f"Failed to insert document: {document_data}")

    document_id = str(db_response.data[0]["id"])
    logger.info(f"Inserted new document {document_id} for sync: {storage_path}")
    return {"document_id": document_id, "is_new": True, "needs_reindex": True}
