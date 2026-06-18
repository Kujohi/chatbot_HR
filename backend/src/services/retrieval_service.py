from typing import List, Dict
import logging
import getpass
import os

from pinecone import Pinecone
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.db.client import get_supabase
from rapidfuzz import fuzz

from src.services.document_service import get_scanned_storage_paths
from src.services.image_document_service import load_scanned_document_images

load_dotenv()

logger = logging.getLogger(__name__)

if not os.getenv("PINECONE_API_KEY"):
    os.environ["PINECONE_API_KEY"] = getpass.getpass("Enter your Pinecone API key: ")

pinecone_api_key = os.environ.get("PINECONE_API_KEY")

pc = Pinecone(api_key=pinecone_api_key)

index_name = os.getenv("PINECONE_INDEX_NAME")  # change if desired
index = pc.Index(index_name)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
vector_store = PineconeVectorStore(index=index, embedding=embeddings)

def format_docs_context(docs: List[Dict]) -> str:
    """
    Format documents context
    """
    doc_context = ""
    for i,doc in enumerate(docs):
        page_number = doc['metadata'].get('page_label') or doc['metadata'].get('page') or 'Unknown'
        doc_context += f"Document {i+1} ('chunk_id': {doc['metadata']['chunk_id']}, 'page_number': {page_number}, 'source': {doc['metadata']['title']}): {doc['page_content']}\n"
    return doc_context

def search_document_summaries(query: str, limit: int = 5) -> List[str]:
    """
    Find relevant documents by matching against summary vectors (isDocument=true).
    Returns storage_path strings (same values stored in documents.storage_path).
    """
    docs = vector_store.similarity_search(
        query,
        k=limit,
        filter={"isDocument": {"$eq": True}},
    )
    document_paths: List[str] = []
    seen_paths = set()
    for doc in docs:
        path = str(doc.metadata.get("storage_path", ""))
        if path and path not in seen_paths:
            seen_paths.add(path)
            document_paths.append(path)
    logger.info(f"Matched {len(document_paths)} document paths for query: {query}")
    return document_paths


def search_text_chunks(document_paths: List[str], hypo_answers: List[str], limit: int = 5) -> str:
    """
    Search chunk vectors in Pinecone for text PDFs, scoped to the given storage paths.
    Matches paths with at least 90% character similarity using rapidfuzz.
    """
    if not document_paths:
        return ""


    try:
        supabase = get_supabase()
        db_res = supabase.table("documents").select("storage_path").execute()
        all_paths = list({doc["storage_path"] for doc in (db_res.data or []) if doc.get("storage_path")})
    except Exception as e:
        logger.error(f"Failed to fetch all paths from database for similarity search: {e}")
        all_paths = []

    matched_paths = set()
    for target_path in document_paths:
        for p in all_paths:
            if fuzz.ratio(p, target_path) >= 90:
                matched_paths.add(p)

    path_filter = list(matched_paths) if matched_paths else [str(path) for path in document_paths]

    all_docs: List[Dict] = []
    seen_contents = set()
    logger.info(f"Search chunks for storage_paths={path_filter}, queries: {hypo_answers}")
    for query in hypo_answers:
        logger.info(f"Search chunks for query: {query}")
        docs = vector_store.similarity_search(
            query,
            k=limit,
            filter={
                "storage_path": {"$in": path_filter},
                "chunk_id": {"$exists": True},
            },
        )
        for doc in docs:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                all_docs.append({"page_content": doc.page_content, "metadata": doc.metadata})
    logger.info(f"Retrieved {len(all_docs)} chunks for hypothesis answers")
    return format_docs_context(all_docs)


def search_documents(document_paths: List[str], hypo_answers: List[str], limit: int = 5) -> Dict:
    """
    Retrieve context for RAG: text chunks for normal PDFs and full-page images for scanned PDFs.
    """
    if not document_paths:
        return {"text_context": "", "image_documents": []}

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

if __name__ == "__main__":
    paths = search_document_summaries("điều kiện dành cho nhân viên nấu bún chả là gì?")
    hypo_answers = ["điều kiện dành cho nhân viên nấu bún chả là gì?"]
    print(search_documents(paths, hypo_answers, limit=2))