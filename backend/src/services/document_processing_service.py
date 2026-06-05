# from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import getpass
import os
import logging
from uuid import uuid4
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
load_dotenv()

logger = logging.getLogger(__name__)

from src.db.client import get_supabase


def split_document(document_id: str):
    supabase = get_supabase()
    response = supabase.table("documents").select("*").eq("id", document_id).execute()
    
    if not response.data:
        raise Exception(f"Document with ID {document_id} not found")
        
    doc_data = response.data[0]
    file_url = doc_data["file_url"]
    
    loader = PyMuPDFLoader(file_url)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    documents = loader.load()
    
    # Fix common Vietnamese PDF extraction errors (e.g. old font encodings)
    for doc in documents:
        doc.page_content = doc.page_content.replace('ƣ', 'ư').replace('Ƣ', 'Ư')
        
    chunks = splitter.split_documents(documents)
    
    # Inject custom metadata into each chunk
    storage_path = doc_data.get("storage_path") or ""
    for chunk in chunks:
        chunk.metadata["document_id"] = str(document_id)
        chunk.metadata["storage_path"] = storage_path
        chunk.metadata["chunk_id"] = str(uuid4())
        chunk.metadata["title"] = doc_data.get("title", "")
        chunk.metadata["owner_id"] = doc_data.get("owner_id", "")
        
    return chunks

def store_document_chunks(chunks: list[Document]):
    supabase = get_supabase()
    insert_data = []
    for chunk in chunks:
        insert_data.append({
            "document_id": chunk.metadata["document_id"],
            "chunk_id": chunk.metadata["chunk_id"],
            "content": chunk.page_content,
        })
        
    if insert_data:
        supabase.table("document_chunks").insert(insert_data).execute()

def document_summary_vector_id(document_id: str) -> str:
    return f"doc-summary-{document_id}"


def pinecone_index_document_summary(
    document_id: str,
    summary: str,
    storage_path: str,
    title: str = "",
    is_image_doc: bool = False,
) -> None:
    """Index a document-level summary vector for routing queries to relevant files."""
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    pc = Pinecone(api_key=pinecone_api_key)
    index_name = os.getenv("PINECONE_INDEX_NAME")
    vector_id = document_summary_vector_id(document_id)

    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            dimension=3072,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(index_name)
    embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
    vector_store = PineconeVectorStore(index=index, embedding=embeddings)

    doc = Document(
        page_content=summary,
        metadata={
            "document_id": str(document_id),
            "isDocument": True,
            "is_image_doc": is_image_doc,
            "storage_path": storage_path,
            "title": title,
        },
    )
    vector_store.add_documents(documents=[doc], ids=[vector_id])
    logger.info(f"Indexed document summary for {document_id} as {vector_id}")


def pinecone_index(chunks: list[Document]):
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    pc = Pinecone(api_key=pinecone_api_key)
    index_name = os.getenv("PINECONE_INDEX_NAME")  # change if desired
    chunk_ids = [chunk.metadata["chunk_id"] for chunk in chunks]

    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            dimension=3072,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(index_name)
    embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
    vector_store = PineconeVectorStore(index=index, embedding=embeddings)
    vector_store.add_documents(documents=chunks, ids=chunk_ids)

def pinecone_delete(chunk_ids: list[str]):
    """
    Deletes a document from the Pinecone index.
    """
    if not chunk_ids:
        logger.info("No chunk IDs provided for Pinecone deletion")
        return
        
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    pc = Pinecone(api_key=pinecone_api_key)
    index_name = os.getenv("PINECONE_INDEX_NAME") 
    index = pc.Index(index_name)
    index.delete(ids=chunk_ids)


if __name__ == "__main__":
    print(len(split_document("17")))