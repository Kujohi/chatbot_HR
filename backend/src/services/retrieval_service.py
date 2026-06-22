from __future__ import annotations

import logging
import unicodedata
from typing import Dict, List

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.db.repositories.vectors import search_vectors
from src.services.document_service import get_scanned_storage_paths
from src.services.image_document_service import load_scanned_document_images

logger = logging.getLogger(__name__)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")


def format_docs_context(docs: List[Dict]) -> str:
    """
    Format documents context
    """
    doc_context = ""
    for i, doc in enumerate(docs):
        metadata = doc.get("metadata") or {}
        page_number = metadata.get("page_label") or metadata.get("page") or "Unknown"
        doc_context += (
            f"Document {i + 1} ('chunk_id': {metadata.get('chunk_id')}, "
            f"'page_number': {page_number}, 'source': {metadata.get('title')}): "
            f"{doc.get('page_content', '')}\n"
        )
    return doc_context


def search_document_summaries(query: str, limit: int = 5) -> List[str]:
    """
    Find relevant documents by matching against summary vectors (isDocument=true).
    Returns storage_path strings (same values stored in documents.storage_path).
    """
    query_embedding = embeddings.embed_query(query)
    docs = search_vectors(query_embedding, limit=limit, is_document=True)

    document_paths: List[str] = []
    seen_paths = set()
    for doc in docs:
        path = str((doc.get("metadata") or {}).get("storage_path", ""))
        if path and path not in seen_paths:
            seen_paths.add(path)
            document_paths.append(path)

    logger.info("Matched %s document paths for query: %s", len(document_paths), query)
    return document_paths


def search_text_chunks(document_paths: List[str], hypo_answers: List[str], limit: int = 5) -> str:
    """
    Search chunk vectors in PostgreSQL for text PDFs, scoped to the given storage paths.
    """
    if not document_paths:
        return ""

    document_paths = [unicodedata.normalize("NFC", str(path)) for path in document_paths]

    all_docs: List[Dict] = []
    seen_contents = set()
    logger.info("Search chunks for storage_paths=%s, queries: %s", document_paths, hypo_answers)
    for query in hypo_answers:
        logger.info("Search chunks for query: %s", query)
        query_embedding = embeddings.embed_query(query)
        docs = search_vectors(
            query_embedding,
            limit=limit,
            is_document=False,
            storage_paths=document_paths,
        )
        for doc in docs:
            content = doc.get("content", "")
            content_hash = hash(content)
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                all_docs.append(
                    {
                        "page_content": content,
                        "metadata": doc.get("metadata") or {},
                    }
                )

    logger.info("Retrieved %s chunks for hypothesis answers", len(all_docs))
    return format_docs_context(all_docs)


def search_documents(document_paths: List[str], hypo_answers: List[str], limit: int = 5) -> Dict:
    """
    Retrieve context for RAG: text chunks for normal PDFs and full-page images for scanned PDFs.
    """
    if not document_paths:
        return {"text_context": "", "image_documents": []}

    document_paths = [unicodedata.normalize("NFC", str(p)) for p in document_paths]

    scanned_paths = set(get_scanned_storage_paths(document_paths))
    text_paths = [path for path in document_paths if path not in scanned_paths]
    image_paths = [path for path in document_paths if path in scanned_paths]
    text_context = search_text_chunks(text_paths, hypo_answers, limit=limit) if text_paths else ""
    image_documents = load_scanned_document_images(image_paths) if image_paths else []

    logger.info(
        "Retrieved %s text paths, %s scanned image paths",
        len(text_paths),
        len(image_documents),
    )
    return {"text_context": text_context, "image_documents": image_documents}
