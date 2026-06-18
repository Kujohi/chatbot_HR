"""Load scanned PDFs as stitched images for multimodal RAG."""

from langchain_community.document_loaders import PyMuPDFLoader
import logging
from typing import List, Dict

from src.services.document_service import (
    get_documents_by_storage_paths,
    get_scanned_storage_paths,
)

logger = logging.getLogger(__name__)
MIN_PAGE_TEXT_CHARS = 100

def is_scanned_pdf(pdf_source: str) -> bool:
    """
    True when the PDF has no meaningful extractable text (image capture / scan).
    Uses the same heuristic as manual inspection: no page exceeds MIN_PAGE_TEXT_CHARS.
    """
    loader = PyMuPDFLoader(pdf_source)
    docs = loader.load()
    if not docs:
        return True
    text_pages = sum(
        1 for doc in docs if len(doc.page_content.strip()) > MIN_PAGE_TEXT_CHARS
    )
    return text_pages == 0


def load_scanned_document_images(storage_paths: List[str]) -> List[Dict]:
    """
    For each scanned-document storage path, load the document reference.
    Returns dicts with title, storage_path, and file_url for LLM vision input.
    """
    if not storage_paths:
        return []

    scanned_paths = set(get_scanned_storage_paths(storage_paths))
    docs = get_documents_by_storage_paths(storage_paths)
    image_docs = [
        doc for doc in docs if doc.get("storage_path") in scanned_paths
    ]
    references: List[Dict] = []

    for doc in image_docs:
        file_url = doc.get("file_url")
        storage_path = doc.get("storage_path")
        sp_item_id = doc.get("sharepoint_item_id")

        if sp_item_id:
            from src.services.sharepoint_sync_service import get_sharepoint_download_url
            try:
                file_url = get_sharepoint_download_url(sp_item_id)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch fresh SharePoint download URL for "
                    f"{storage_path} (id={doc.get('id')}): {e}. "
                    f"Falling back to stored URL."
                )

        if not file_url or not storage_path:
            continue
        references.append(
            {
                "document_id": doc.get("id"),
                "title": doc.get("title") or storage_path,
                "storage_path": storage_path,
                "file_url": file_url,
            }
        )
        logger.info(f"Loaded scanned PDF file reference for {storage_path}")

    return references
