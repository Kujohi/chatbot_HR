import logging
import re
import unicodedata

from src.db.client import get_supabase
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = unicodedata.normalize("NFKD", slug)
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "folder"


def get_folder(folder_id: int) -> dict | None:
    supabase = get_supabase()
    response = (
        supabase.table("document_folders")
        .select("*")
        .eq("id", folder_id)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0]


def get_folder_breadcrumb(folder_id: int):
    try:
        chain = []
        current_id = folder_id
        while current_id is not None:
            folder = get_folder(current_id)
            if not folder:
                break
            chain.insert(0, {"id": folder["id"], "name": folder["name"], "path": folder["path"]})
            current_id = folder.get("parent_id")
        return {"status": "success", "data": chain}
    except Exception as e:
        logger.error(f"Error building breadcrumb: {e}")
        return {"status": "error", "message": str(e)}


def list_folders(parent_id: int | None = None):
    """List child folders for a parent. parent_id=None returns root-level folders."""
    try:
        supabase = get_supabase()
        query = supabase.table("document_folders").select("*").order("name")
        if parent_id is None:
            query = query.is_("parent_id", "null")
        else:
            query = query.eq("parent_id", parent_id)

        folders = query.execute()
        all_folders = supabase.table("document_folders").select("id, parent_id").execute()
        child_counts: dict[int, int] = {}
        for row in all_folders.data or []:
            pid = row.get("parent_id")
            if pid is not None:
                child_counts[pid] = child_counts.get(pid, 0) + 1

        docs = supabase.table("documents").select("id, folder_id").execute()
        doc_counts: dict[int, int] = {}
        for doc in docs.data or []:
            fid = doc.get("folder_id")
            if fid is not None:
                doc_counts[fid] = doc_counts.get(fid, 0) + 1

        data = []
        for folder in folders.data or []:
            row = dict(folder)
            row["subfolder_count"] = child_counts.get(folder["id"], 0)
            row["document_count"] = doc_counts.get(folder["id"], 0)
            data.append(row)

        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error listing folders: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Sync helpers — used by sharepoint_sync_service
# ---------------------------------------------------------------------------

def get_or_create_folder_for_path(path_segments: list[str]) -> int:
    """
    Walk the path segments top-down, creating document_folders rows as needed.
    Returns the leaf folder ID.

    Example: ["HR", "Policies"] creates:
      - HR        (parent_id=None, path="hr")
      - Policies  (parent_id=<HR id>, path="hr/policies")
    """
    supabase = get_supabase()
    parent_id: int | None = None
    current_path = ""

    for segment in path_segments:
        slug = slugify(segment)
        current_path = f"{current_path}/{slug}" if current_path else slug

        existing = (
            supabase.table("document_folders")
            .select("id")
            .eq("path", current_path)
            .limit(1)
            .execute()
        )
        if existing.data:
            parent_id = existing.data[0]["id"]
            continue

        response = (
            supabase.table("document_folders")
            .insert(
                {
                    "name": segment.strip(),
                    "slug": slug,
                    "path": current_path,
                    "parent_id": parent_id,
                    "description": "",
                    "created_by": "sharepoint_sync",
                }
            )
            .execute()
        )
        if not response.data:
            raise Exception(f"Failed to create folder at path {current_path}")
        parent_id = response.data[0]["id"]
        logger.info(f"Created folder '{segment}' at path {current_path} (id={parent_id})")

    if parent_id is None:
        raise Exception("Cannot create folder for empty path segments")
    return parent_id


def delete_empty_folders() -> int:
    """
    Remove folders that have no documents and no sub-folders.
    Repeats until no more empty folders are found (handles nested empties).
    Returns total count of deleted folders.
    """
    supabase = get_supabase()
    total_deleted = 0

    while True:
        all_folders = supabase.table("document_folders").select("id, parent_id").execute()
        docs = supabase.table("documents").select("folder_id").execute()

        folder_ids = {f["id"] for f in (all_folders.data or [])}
        parent_ids = {f["parent_id"] for f in (all_folders.data or []) if f.get("parent_id")}
        doc_folder_ids = {d["folder_id"] for d in (docs.data or []) if d.get("folder_id")}

        # A folder is empty if it has no sub-folders and no documents
        empty_ids = folder_ids - parent_ids - doc_folder_ids
        if not empty_ids:
            break

        for fid in empty_ids:
            supabase.table("document_folders").delete().eq("id", fid).execute()
            logger.info(f"Deleted empty folder id={fid}")

        total_deleted += len(empty_ids)

    return total_deleted
