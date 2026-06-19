"""
SharePoint Sync Service
=======================
Syncs documents from a SharePoint drive into the app's database and Pinecone index.
Runs as a background cronjob (every 5 minutes) and on startup.

Key behaviors:
- Walks the SharePoint drive recursively, processes PDF and DOCX files.
- Detects new, modified, and deleted files using sharepoint_item_id + lastModifiedDateTime.
- On Gemini API rate-limit errors, stops the sync immediately without storing the
  partially-processed file; the next cycle will resume where it left off.
"""

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from msal import ConfidentialClientApplication
from dotenv import load_dotenv

from src.db.client import get_supabase
from src.services.document_service import (
    upsert_document_for_sync,
    index_docs,
    rollback_document,
    delete_document,
)
from src.services.folder_service import (
    get_or_create_folder_for_path,
    delete_empty_folders,
)
from src.utils.utils import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def _source_type_from_name(file_name: str) -> str | None:
    """Return the source_type string for a supported file, or None if unsupported."""
    if file_name.startswith("~$"):
        return None
    ext = os.path.splitext(file_name)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a Gemini/Google API rate-limit error."""
    exc_str = str(exc).lower()
    if "429" in exc_str or "resource_exhausted" in exc_str or "resourceexhausted" in exc_str:
        return True

    # Check exception type names for google API errors
    exc_type = type(exc).__name__
    if exc_type in ("ResourceExhausted", "TooManyRequests"):
        return True

    # Check wrapped cause
    cause = getattr(exc, "__cause__", None)
    if cause:
        return _is_rate_limit_error(cause)

    return False


# ---------------------------------------------------------------------------
# Microsoft Graph Auth
# ---------------------------------------------------------------------------

def _get_access_token() -> str:
    """Acquire a fresh access token using MSAL client credentials."""
    tenant_id = os.environ["SHAREPOINT_TENANT_ID"]
    client_id = os.environ["SHAREPOINT_CLIENT_ID"]
    client_secret = os.environ["SHAREPOINT_CLIENT_SECRET"]

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise Exception(f"Failed to acquire SharePoint access token: {result}")

    return result["access_token"]


# ---------------------------------------------------------------------------
# SharePoint Drive Walking
# ---------------------------------------------------------------------------

@dataclass
class SharePointFile:
    item_id: str
    path: str  # relative path from root folder, e.g. "HR/Policies/leave.pdf"
    download_url: str
    last_modified: str  # ISO 8601 timestamp
    name: str


def _walk_drive_folder(
    drive_id: str,
    item_id: str,
    headers: dict,
    current_path: str = "",
) -> list[SharePointFile]:
    """Recursively list all files under a SharePoint drive folder."""
    url = (
        f"https://graph.microsoft.com/v1.0/"
        f"drives/{drive_id}/items/{item_id}/children"
    )
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    files: list[SharePointFile] = []
    for item in r.json().get("value", []):
        rel_path = f"{current_path}/{item['name']}" if current_path else item["name"]

        if "folder" in item:
            files.extend(
                _walk_drive_folder(drive_id, item["id"], headers, rel_path)
            )
        else:
            download_url = item.get("@microsoft.graph.downloadUrl", "")
            last_modified = item.get("lastModifiedDateTime", "")
            files.append(
                SharePointFile(
                    item_id=item["id"],
                    path=rel_path,
                    download_url=download_url,
                    last_modified=last_modified,
                    name=item["name"],
                )
            )

    return files


def _get_all_sharepoint_files(headers: dict) -> list[SharePointFile]:
    """Get all files from the configured SharePoint drive/root folder."""
    drive_id = os.environ["SHAREPOINT_DRIVE_ID"]
    root_folder = os.environ.get("SHAREPOINT_ROOT_FOLDER", "")

    if root_folder:
        # Get the root folder item first
        url = (
            f"https://graph.microsoft.com/v1.0/"
            f"drives/{drive_id}/root:/{root_folder}:/children"
        )
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        files: list[SharePointFile] = []
        for item in r.json().get("value", []):
            if "folder" in item:
                files.extend(
                    _walk_drive_folder(drive_id, item["id"], headers, item["name"])
                )
            else:
                download_url = item.get("@microsoft.graph.downloadUrl", "")
                last_modified = item.get("lastModifiedDateTime", "")
                files.append(
                    SharePointFile(
                        item_id=item["id"],
                        path=item["name"],
                        download_url=download_url,
                        last_modified=last_modified,
                        name=item["name"],
                    )
                )
        return files
    else:
        # Walk from drive root
        url = (
            f"https://graph.microsoft.com/v1.0/"
            f"drives/{drive_id}/root/children"
        )
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        files = []
        for item in r.json().get("value", []):
            if "folder" in item:
                files.extend(
                    _walk_drive_folder(drive_id, item["id"], headers, item["name"])
                )
            else:
                download_url = item.get("@microsoft.graph.downloadUrl", "")
                last_modified = item.get("lastModifiedDateTime", "")
                files.append(
                    SharePointFile(
                        item_id=item["id"],
                        path=item["name"],
                        download_url=download_url,
                        last_modified=last_modified,
                        name=item["name"],
                    )
                )
        return files


# ---------------------------------------------------------------------------
# Sync Result
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    new_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    deleted_count: int = 0
    error_count: int = 0
    stopped_by_rate_limit: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "new": self.new_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "deleted": self.deleted_count,
            "errors": self.error_count,
            "stopped_by_rate_limit": self.stopped_by_rate_limit,
            "error_details": self.errors[:10],  # limit error details
        }


# ---------------------------------------------------------------------------
# Core Sync Logic
# ---------------------------------------------------------------------------

def run_sync() -> SyncResult:
    """
    Main sync entry point. Call this from the background task or /sync endpoint.
    Returns a SyncResult summarizing what happened.
    """
    result = SyncResult()

    try:
        access_token = _get_access_token()
    except Exception as e:
        logger.error(f"SharePoint auth failed: {e}")
        result.errors.append(f"Auth failed: {e}")
        result.error_count += 1
        return result

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        remote_files = _get_all_sharepoint_files(headers)
    except Exception as e:
        logger.error(f"Failed to list SharePoint files: {e}")
        result.errors.append(f"File listing failed: {e}")
        result.error_count += 1
        return result

    logger.debug(f"SharePoint sync: found {len(remote_files)} total files")

    # Track which sharepoint_item_ids we see (for deletion detection)
    seen_item_ids: set[str] = set()

    for sp_file in remote_files:
        source_type = _source_type_from_name(sp_file.name)
        if source_type is None:
            # Unsupported file type, skip
            continue

        seen_item_ids.add(sp_file.item_id)

        # Derive folder path segments from the SharePoint path
        path_parts = sp_file.path.split("/")
        folder_segments = path_parts[:-1]  # everything except the filename
        storage_path = sp_file.path  # full relative path as storage_path

        try:
            # Ensure folder hierarchy exists
            if folder_segments:
                folder_id = get_or_create_folder_for_path(folder_segments)
            else:
                # File at root level — create a "root" folder
                folder_id = get_or_create_folder_for_path(["Root"])

            # Upsert document metadata
            upsert_result = upsert_document_for_sync(
                title=sp_file.name,
                file_url=sp_file.download_url,
                storage_path=storage_path,
                folder_id=folder_id,
                source_type=source_type,
                sharepoint_item_id=sp_file.item_id,
                sharepoint_modified_at=sp_file.last_modified,
            )

            document_id = upsert_result["document_id"]

            if not upsert_result["needs_reindex"]:
                result.skipped_count += 1
                continue

            # Index the document (this calls Gemini for embeddings + summary)
            index_docs(document_id)

            # Mark as indexed
            get_supabase().table("documents").update(
                {"status": "indexed"}
            ).eq("id", int(document_id)).execute()

            if upsert_result["is_new"]:
                result.new_count += 1
                logger.info(f"Synced new document: {sp_file.path}")
            else:
                result.updated_count += 1
                logger.info(f"Re-indexed updated document: {sp_file.path}")

        except Exception as e:
            if _is_rate_limit_error(e):
                logger.warning(
                    f"Gemini rate limit hit while processing {sp_file.path} — "
                    f"stopping sync. Will resume on next cycle."
                )
                # Rollback the document if it was just inserted
                try:
                    rollback_document(upsert_result["document_id"])
                except Exception:
                    pass  # best effort
                result.stopped_by_rate_limit = True
                return result

            # Non-rate-limit error — skip this file, continue with others
            logger.error(f"Failed to sync {sp_file.path}: {e}")
            try:
                rollback_document(upsert_result["document_id"])
            except Exception:
                pass
            result.error_count += 1
            result.errors.append(f"{sp_file.path}: {e}")
            continue

    # --- Deletion detection ---
    # Only run if we weren't stopped by rate limit (we have a complete file list)
    if not result.stopped_by_rate_limit:
        try:
            supabase = get_supabase()
            all_docs = (
                supabase.table("documents")
                .select("id, sharepoint_item_id, storage_path")
                .not_.is_("sharepoint_item_id", "null")
                .execute()
            )
            for doc in (all_docs.data or []):
                if doc["sharepoint_item_id"] not in seen_item_ids:
                    logger.info(
                        f"Deleting document no longer in SharePoint: "
                        f"{doc.get('storage_path')} (id={doc['id']})"
                    )
                    delete_document(str(doc["id"]))
                    result.deleted_count += 1

            # Clean up empty folders
            deleted_folders = delete_empty_folders()
            if deleted_folders:
                logger.info(f"Cleaned up {deleted_folders} empty folders")

        except Exception as e:
            logger.error(f"Error during deletion cleanup: {e}")
            result.errors.append(f"Deletion cleanup: {e}")

    has_activity = (
        result.new_count > 0 or
        result.updated_count > 0 or
        result.deleted_count > 0 or
        result.error_count > 0
    )
    if has_activity:
        logger.info(
            f"Sync complete: {result.new_count} new, {result.updated_count} updated, "
            f"{result.skipped_count} skipped, {result.deleted_count} deleted, "
            f"{result.error_count} errors, rate_limited={result.stopped_by_rate_limit}"
        )
    else:
        logger.debug(
            f"Sync complete: {result.new_count} new, {result.updated_count} updated, "
            f"{result.skipped_count} skipped, {result.deleted_count} deleted, "
            f"{result.error_count} errors, rate_limited={result.stopped_by_rate_limit}"
        )
    return result


def get_sharepoint_download_url(sharepoint_item_id: str) -> str:
    """Fetch a fresh download URL for a specific SharePoint item ID."""
    access_token = _get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    drive_id = os.environ["SHAREPOINT_DRIVE_ID"]

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{sharepoint_item_id}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    download_url = r.json().get("@microsoft.graph.downloadUrl", "")
    if not download_url:
        raise Exception(f"No download URL found in SharePoint item {sharepoint_item_id}")
    return download_url


def get_sharepoint_web_url(sharepoint_item_id: str) -> str:
    """Fetch the permanent webUrl (view URL) for a specific SharePoint item ID."""
    access_token = _get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    drive_id = os.environ["SHAREPOINT_DRIVE_ID"]

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{sharepoint_item_id}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    web_url = r.json().get("webUrl", "")
    if not web_url:
        raise Exception(f"No webUrl found in SharePoint item {sharepoint_item_id}")
    return web_url


