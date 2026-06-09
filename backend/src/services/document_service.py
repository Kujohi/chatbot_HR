from src.db.client import get_supabase
import logging
import urllib.parse
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
from src.services.folder_service import get_folder, build_storage_path
from src.services.rewriter import rewrite_path_to_summary

setup_logging()
logger = logging.getLogger(__name__)

BUCKET_NAME = "documents"


def _storage_path_from_url(file_url: str) -> str | None:
    url_parts = file_url.split(f"/public/{BUCKET_NAME}/")
    if len(url_parts) > 1:
        return urllib.parse.unquote(url_parts[1])
    return None


def _remove_storage_file(file_url: str | None = None, storage_path: str | None = None) -> None:
    file_path = storage_path or (file_url and _storage_path_from_url(file_url))
    if not file_path:
        return
    supabase = get_supabase()
    logger.info(f"Deleting file from storage: {file_path}")
    supabase.storage.from_(BUCKET_NAME).remove([file_path])


def _cleanup_document_index(document_id: str) -> None:
    """Remove Pinecone vectors and chunk rows; keep the documents row and storage file."""
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
    Remove Supabase storage, document_chunks rows, and documents row after indexing fails.
    Best-effort Pinecone cleanup if any vectors were partially written.
    """
    supabase = get_supabase()
    doc_response = supabase.table("documents").select("*").eq("id", document_id).execute()
    if not doc_response.data:
        logger.warning(f"Rollback skipped: document {document_id} not found")
        return

    document = doc_response.data[0]
    file_url = document.get("file_url")

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

    storage_path = document.get("storage_path")
    if file_url or storage_path:
        try:
            _remove_storage_file(file_url, storage_path)
        except Exception as storage_e:
            logger.warning(f"Rollback: failed to delete storage file: {storage_e}")

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
        .select("id, title, file_url, storage_path, is_image_pdf")
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


def insert_docs(file_content, file_name, title, owner_id, folder_id: int, source_type="pdf"):
    """
    Upload a document to Supabase storage and upsert metadata.
    Replaces an existing document in the same folder when the file name matches.
    """
    try:
        logger.info(f"Inserting document: {title} for owner: {owner_id} in folder {folder_id}")
        folder = get_folder(folder_id)
        if not folder:
            return {"status": "error", "message": "Folder not found"}

        supabase = get_supabase()
        file_path = build_storage_path(folder["path"], file_name)
        upload_options = {"upsert": "true"}
        if source_type == "pdf":
            upload_options["content-type"] = "application/pdf"

        supabase.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=file_content,
            file_options=upload_options,
        )

        file_url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
        existing = _find_document_in_folder(folder_id, file_path)
        replaced = existing is not None

        if replaced:
            document_id = existing["id"]
            logger.info(f"Replacing existing document {document_id} at {file_path}")
            _cleanup_document_index(document_id)
            update_data = {
                "title": title,
                "source_type": source_type,
                "file_url": file_url,
                "storage_path": file_path,
                "owner_id": owner_id,
                "status": "uploaded",
                "is_image_pdf": False,
            }
            db_response = (
                supabase.table("documents")
                .update(update_data)
                .eq("id", document_id)
                .execute()
            )
            if not db_response.data:
                raise Exception(f"Failed to update document metadata: {db_response}")
        else:
            document_data = {
                "title": title,
                "source_type": source_type,
                "file_url": file_url,
                "storage_path": file_path,
                "folder_id": folder_id,
                "owner_id": owner_id,
                "status": "uploaded",
            }
            logger.info(f"Inserting metadata into documents table: {document_data}")
            db_response = supabase.table("documents").insert(document_data).execute()
            if not db_response.data:
                raise Exception(f"Failed to insert document metadata: {db_response}")
            document_id = db_response.data[0]["id"]
            logger.info(f"Document inserted successfully with ID: {document_id}")

        return {
            "status": "success",
            "document_id": document_id,
            "file_url": file_url,
            "storage_path": file_path,
            "replaced": replaced,
            "file_name": file_name,
        }

    except Exception as e:
        logger.error(f"Error in insert_docs: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
        }


def create_and_index_document(
    file_content: bytes,
    file_name: str,
    title: str,
    owner_id: str,
    folder_id: int,
    source_type: str = "pdf",
) -> dict:
    """Upload (or replace) one document and index it. Returns error dict on failure."""
    create_status = insert_docs(
        file_content=file_content,
        file_name=file_name,
        title=title,
        owner_id=owner_id,
        folder_id=folder_id,
        source_type=source_type,
    )
    if create_status.get("status") != "success":
        return create_status

    document_id = create_status["document_id"]
    replaced = create_status.get("replaced", False)
    try:
        index_docs(document_id)
    except Exception as index_error:
        logger.error(f"Indexing failed for document {document_id}: {index_error}")
        try:
            if replaced:
                _cleanup_document_index(document_id)
                get_supabase().table("documents").update(
                    {"status": "index_failed"}
                ).eq("id", document_id).execute()
            else:
                rollback_document(document_id)
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed for document {document_id}: {cleanup_error}")
        return {
            "status": "error",
            "message": f"Failed to create vector embeddings: {index_error}",
            "file_name": file_name,
        }

    return create_status


def insert_docs_batch(
    files: list[tuple[bytes, str, str]],
    owner_id: str,
    folder_id: int,
    source_type: str = "pdf",
) -> dict:
    """
    Upload and index multiple documents sequentially.
    Stops on the first failure; earlier files remain uploaded/indexed.
    """
    uploaded: list[dict] = []
    for file_content, file_name, title in files:
        result = create_and_index_document(
            file_content=file_content,
            file_name=file_name,
            title=title,
            owner_id=owner_id,
            folder_id=folder_id,
            source_type=source_type,
        )
        if result.get("status") != "success":
            return {
                "status": "error",
                "message": result.get("message", "Upload failed"),
                "failed_file": file_name,
                "uploaded": uploaded,
                "completed_count": len(uploaded),
                "total_count": len(files),
            }
        uploaded.append(
            {
                "document_id": result["document_id"],
                "file_name": file_name,
                "storage_path": result.get("storage_path"),
                "replaced": result.get("replaced", False),
            }
        )

    return {
        "status": "success",
        "data": uploaded,
        "completed_count": len(uploaded),
        "total_count": len(files),
    }

def index_docs(document_id: str) -> None:
    """
    Indexes a document into Pinecone.
    Text PDFs: summary vector + content chunks.
    Scanned/image PDFs: summary vector only (no chunking).
    Raises on failure so callers can roll back the Supabase upload.
    """
    supabase = get_supabase()
    response = (
        supabase.table("documents")
        .select("storage_path, title, file_url")
        .eq("id", document_id)
        .execute()
    )
    if not response.data:
        raise Exception(f"Document with ID {document_id} not found")

    doc_data = response.data[0]
    storage_path = doc_data.get("storage_path")
    file_url = doc_data.get("file_url")
    if not storage_path:
        raise Exception(f"Document {document_id} has no storage_path")
    if not file_url:
        raise Exception(f"Document {document_id} has no file_url")

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
            },
        }

        return {"status": "success", "data": formatted_data}
    except Exception as e:
        logger.error(f"Error fetching chunk: {str(e)}")
        return {"status": "error", "message": str(e)}

def delete_document(document_id: str):
    """
    Deletes a document from the documents table and Supabase storage.
    """
    try:
        supabase = get_supabase()
        
        # 1. Get document metadata to find the file path
        doc_response = supabase.table("documents").select("*").eq("id", document_id).execute()
        chunk_response = supabase.table("document_chunks").select("*").eq("document_id", document_id).execute()

        if not doc_response.data:
            return {"status": "error", "message": "Document not found"}
            
        document = doc_response.data[0]
        file_url = document.get("file_url")
        storage_path = document.get("storage_path")

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
                # Continue with other deletions even if Pinecone fails

        # 3. Delete chunk rows from database
        supabase.table("document_chunks").delete().eq("document_id", document_id).execute()

        # 4. Delete from storage
        if file_url or storage_path:
            try:
                _remove_storage_file(file_url, storage_path)
            except Exception as storage_e:
                logger.warning(f"Failed to delete file from storage: {str(storage_e)}")

        # 5. Delete from database
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
