from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import os
import uvicorn
import logging
from src.utils.utils import setup_logging
from src.services.chat_service import llm_handle_message
from src.services.document_service import (
    get_all_documents,
    get_chunk,
)
from src.services.folder_service import (
    list_folders,
    get_folder_breadcrumb,
)

TASK_TIMEOUT = 60
POLLING_INTERVAL = 0.5

setup_logging()
logger = logging.getLogger(__name__)


SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_SECONDS", "10"))
_sync_lock = asyncio.Lock()


async def _sync_loop():
    """Run SharePoint sync on startup and then every SYNC_INTERVAL seconds."""
    from src.services.sharepoint_sync_service import run_sync

    while True:
        try:
            async with _sync_lock:
                logger.debug("Starting SharePoint sync cycle...")
                result = await asyncio.to_thread(run_sync)
                has_activity = (
                    result.new_count > 0 or
                    result.updated_count > 0 or
                    result.deleted_count > 0 or
                    result.error_count > 0
                )
                if has_activity:
                    logger.info(f"Sync cycle finished: {result.to_dict()}")
                else:
                    logger.debug(f"Sync cycle finished: {result.to_dict()}")
        except Exception as e:
            logger.error(f"Sync cycle failed: {e}")
        await asyncio.sleep(SYNC_INTERVAL)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: starts background sync on startup, cancels on shutdown."""
    task = asyncio.create_task(_sync_loop())
    logger.info(f"SharePoint sync background task started (interval={SYNC_INTERVAL}s)")
    yield
    task.cancel()
    logger.info("SharePoint sync background task cancelled")


app = FastAPI(lifespan=lifespan)

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


@router.get("/documents")
async def get_documents(folder_id: int | None = Query(default=None)):
    logger.info(f"Fetching documents (folder_id={folder_id})")
    return await asyncio.to_thread(get_all_documents, folder_id)

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


@router.post("/sync")
async def trigger_sync():
    """Manually trigger a SharePoint sync (admin use)."""
    if _sync_lock.locked():
        logger.warning("Manual sync requested but a sync cycle is already in progress")
        return {"status": "error", "message": "A sync cycle is already in progress"}

    async with _sync_lock:
        logger.info("Manual sync triggered via API")
        from src.services.sharepoint_sync_service import run_sync
        try:
            result = await asyncio.to_thread(run_sync)
            return {"status": "success", "data": result.to_dict()}
        except Exception as e:
            logger.error(f"Manual sync failed: {e}")
            return {"status": "error", "message": str(e)}


@router.get("/documents/{document_id}/view")
async def view_document(document_id: str):
    """
    Get the SharePoint web view URL for a document on-the-fly,
    and redirect the client to it.
    """
    from src.db.client import get_supabase
    from fastapi.responses import RedirectResponse
    from fastapi import HTTPException

    try:
        supabase = get_supabase()
        response = await asyncio.to_thread(
            lambda: supabase.table("documents")
            .select("sharepoint_item_id, file_url")
            .eq("id", int(document_id))
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data[0]
        sp_item_id = doc.get("sharepoint_item_id")
        file_url = doc.get("file_url")

        if sp_item_id:
            from src.services.sharepoint_sync_service import get_sharepoint_web_url
            try:
                web_url = await asyncio.to_thread(get_sharepoint_web_url, sp_item_id)
                return RedirectResponse(url=web_url)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch SharePoint web view URL for document "
                    f"{document_id}: {e}. Redirecting to stored URL instead."
                )

        if file_url:
            return RedirectResponse(url=file_url)

        raise HTTPException(status_code=404, detail="No view URL available")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling view redirect for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)