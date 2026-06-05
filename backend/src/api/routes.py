from fastapi import FastAPI, APIRouter, File, UploadFile, Form, Query
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import uvicorn
import logging
from src.utils.utils import setup_logging
from src.services.chat_service import llm_handle_message
from src.services.document_service import (
    create_and_index_document,
    insert_docs_batch,
    get_all_documents,
    delete_document,
    get_chunk,
)
from src.services.folder_service import (
    list_folders,
    create_folder,
    delete_folder,
    get_folder_breadcrumb,
)

TASK_TIMEOUT = 60
POLLING_INTERVAL = 0.5

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

class ChatCompleteRequest(BaseModel):
    thread_id: str
    message: str
    bot_id: str
    sync_request: bool


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: int | None = None
    description: str = ""
    created_by: str = ""

@router.get("/health")
async def health():
    return {"message": "Healthy"}

@router.post("/chat/complete")
async def chat_complete(request: ChatCompleteRequest):
    thread_id = request.thread_id
    message = request.message
    sync_request = request.sync_request
    logger.info(f"Complete chat from user {thread_id}: {message}")
    if sync_request:
        response = await asyncio.to_thread(llm_handle_message, thread_id, message)
        return {"response": response}

@router.get("/folders")
async def list_folders_endpoint(parent_id: int | None = Query(default=None)):
    logger.info(f"Listing folders (parent_id={parent_id})")
    return await asyncio.to_thread(list_folders, parent_id)


@router.get("/folders/{folder_id}/breadcrumb")
async def folder_breadcrumb_endpoint(folder_id: int):
    return await asyncio.to_thread(get_folder_breadcrumb, folder_id)


@router.post("/folders")
async def create_folder_endpoint(request: CreateFolderRequest):
    logger.info(f"Creating folder: {request.name} under parent {request.parent_id}")
    return await asyncio.to_thread(
        create_folder,
        request.name,
        request.parent_id,
        request.description,
        request.created_by,
    )


@router.delete("/folders/{folder_id}")
async def delete_folder_endpoint(folder_id: int):
    logger.info(f"Deleting folder: {folder_id}")
    return await asyncio.to_thread(delete_folder, folder_id)


@router.post("/document/create")
async def create_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    owner_id: str = Form("default_user"),
    folder_id: int = Form(...),
    source_type: str = Form("pdf"),
):
    logger.info(f"Creating document: {title} for owner: {owner_id} in folder: {folder_id}")
    try:
        file_content = await file.read()
        return await asyncio.to_thread(
            create_and_index_document,
            file_content=file_content,
            file_name=file.filename or "document.pdf",
            title=title or file.filename or "document.pdf",
            owner_id=owner_id,
            folder_id=folder_id,
            source_type=source_type,
        )
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/document/create-batch")
async def create_documents_batch(
    files: List[UploadFile] = File(...),
    owner_id: str = Form("default_user"),
    folder_id: int = Form(...),
    source_type: str = Form("pdf"),
):
    logger.info(f"Batch creating {len(files)} documents in folder: {folder_id}")
    if not files:
        return {"status": "error", "message": "No files provided"}

    try:
        batch_files = []
        for upload in files:
            content = await upload.read()
            file_name = upload.filename or "document.pdf"
            batch_files.append((content, file_name, file_name))

        return await asyncio.to_thread(
            insert_docs_batch,
            files=batch_files,
            owner_id=owner_id,
            folder_id=folder_id,
            source_type=source_type,
        )
    except Exception as e:
        logger.error(f"Error in batch document create: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.get("/documents")
async def get_documents(folder_id: int | None = Query(default=None)):
    logger.info(f"Fetching documents (folder_id={folder_id})")
    return await asyncio.to_thread(get_all_documents, folder_id)

@router.delete("/document/{document_id}")
async def delete_doc(document_id: str):
    logger.info(f"Deleting document: {document_id}")
    return await asyncio.to_thread(delete_document, document_id)

@router.get("/chunk/{chunk_id}")
async def get_chunk_endpoint(chunk_id: str):
    logger.info(f"Fetching chunk: {chunk_id}")
    return await asyncio.to_thread(get_chunk, chunk_id)

@router.get("/chat/conversation/{thread_id}")
async def get_conversation(thread_id: str):
    logger.info(f"Fetching conversation for thread: {thread_id}")
    from src.services.conversation import get_conversation_messages
    try:
        messages = await asyncio.to_thread(get_conversation_messages, thread_id)
        return {"status": "success", "data": messages}
    except Exception as e:
        logger.error(f"Error fetching conversation: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.delete("/chat/conversation/{thread_id}")
async def delete_conversation(thread_id: str):
    logger.info(f"Deleting conversation thread: {thread_id}")
    from src.db.client import get_supabase
    try:
        supabase = get_supabase()
        await asyncio.to_thread(
            lambda: supabase.table("threads").delete().eq("id", thread_id).execute()
        )
        return {"status": "success", "message": "Thread deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting thread: {str(e)}")
        return {"status": "error", "message": str(e)}

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)