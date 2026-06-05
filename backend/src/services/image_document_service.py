"""Load scanned PDFs as stitched images for multimodal RAG."""

import logging
from typing import List, Dict

from src.pdf_image import pdf_to_vertical_image_base64
from src.services.document_service import (
    get_documents_by_storage_paths,
    get_scanned_storage_paths,
)

logger = logging.getLogger(__name__)


def load_scanned_document_images(storage_paths: List[str]) -> List[Dict]:
    """
    For each scanned-document storage path, render the full PDF as one vertical image.
    Returns dicts with title, storage_path, base64, and mime_type for LLM vision input.
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
        if not file_url or not storage_path:
            continue
        try:
            image_base64, mime_type = pdf_to_vertical_image_base64(file_url)
            references.append(
                {
                    "document_id": doc.get("id"),
                    "title": doc.get("title") or storage_path,
                    "storage_path": storage_path,
                    "base64": image_base64,
                    "mime_type": mime_type,
                }
            )
            logger.info(f"Loaded scanned PDF image reference for {storage_path}")
        except Exception as error:
            logger.error(f"Failed to render scanned PDF {storage_path}: {error}")

    return references
