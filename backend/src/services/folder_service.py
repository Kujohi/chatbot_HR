import logging
import re
import unicodedata

from src.db.client import get_supabase
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Supabase Storage object keys must be ASCII-safe (no Vietnamese diacritics, etc.)
_VIET_ASCII = str.maketrans(
    {
        "đ": "d",
        "Đ": "D",
        "ă": "a",
        "Ă": "A",
        "â": "a",
        "Â": "A",
        "ê": "e",
        "Ê": "E",
        "ô": "o",
        "Ô": "O",
        "ơ": "o",
        "Ơ": "O",
        "ư": "u",
        "Ư": "U",
    }
)


def to_ascii_storage_key(text: str) -> str:
    text = text.translate(_VIET_ASCII)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def sanitize_storage_segment(segment: str) -> str:
    segment = to_ascii_storage_key(segment.strip())
    segment = re.sub(r"[^\w.\-]", "_", segment)
    segment = re.sub(r"_+", "_", segment).strip("_")
    return segment or "item"


def slugify(name: str) -> str:
    slug = to_ascii_storage_key(name.lower().strip())
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


def _unique_path(base_path: str) -> str:
    supabase = get_supabase()
    path = base_path
    suffix = 2
    while True:
        existing = (
            supabase.table("document_folders")
            .select("id")
            .eq("path", path)
            .execute()
        )
        if not existing.data:
            return path
        path = f"{base_path}-{suffix}"
        suffix += 1


def _build_folder_path(parent_id: int | None, slug: str) -> str:
    if parent_id is None:
        return slug
    parent = get_folder(parent_id)
    if not parent:
        raise ValueError("Parent folder not found")
    return f"{parent['path']}/{slug}"


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


def create_folder(name: str, parent_id: int | None = None, description: str = "", created_by: str = ""):
    try:
        name = name.strip()
        if not name:
            return {"status": "error", "message": "Folder name is required"}

        if parent_id is not None and not get_folder(parent_id):
            return {"status": "error", "message": "Parent folder not found"}

        slug = slugify(name)
        path = _unique_path(_build_folder_path(parent_id, slug))
        slug = path.split("/")[-1]

        supabase = get_supabase()
        response = (
            supabase.table("document_folders")
            .insert(
                {
                    "name": name,
                    "slug": slug,
                    "path": path,
                    "parent_id": parent_id,
                    "description": description.strip(),
                    "created_by": created_by,
                }
            )
            .execute()
        )
        if not response.data:
            return {"status": "error", "message": "Failed to create folder"}

        folder = response.data[0]
        folder["subfolder_count"] = 0
        folder["document_count"] = 0
        logger.info(f"Created folder {folder['id']} at path {path}")
        return {"status": "success", "data": folder}
    except Exception as e:
        logger.error(f"Error creating folder: {e}")
        return {"status": "error", "message": str(e)}


def delete_folder(folder_id: int):
    try:
        folder = get_folder(folder_id)
        if not folder:
            return {"status": "error", "message": "Folder not found"}

        if folder.get("slug") == "general" and folder.get("parent_id") is None:
            return {"status": "error", "message": "Cannot delete the default General folder"}

        supabase = get_supabase()

        subfolders = (
            supabase.table("document_folders")
            .select("id")
            .eq("parent_id", folder_id)
            .execute()
        )
        if subfolders.data:
            return {
                "status": "error",
                "message": "Folder is not empty. Delete or move subfolders first.",
            }

        docs = (
            supabase.table("documents")
            .select("id")
            .eq("folder_id", folder_id)
            .execute()
        )
        if docs.data:
            return {
                "status": "error",
                "message": "Folder is not empty. Delete documents first.",
            }

        supabase.table("document_folders").delete().eq("id", folder_id).execute()
        logger.info(f"Deleted folder {folder_id}")
        return {"status": "success", "message": "Folder deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting folder: {e}")
        return {"status": "error", "message": str(e)}


def build_storage_path(folder_path: str, file_name: str) -> str:
    base = file_name.split("/")[-1] if file_name else "document.pdf"
    stem, _, ext = base.rpartition(".")
    if ext:
        safe_name = f"{sanitize_storage_segment(stem or 'document')}.{sanitize_storage_segment(ext)}"
    else:
        safe_name = sanitize_storage_segment(base) or "document.pdf"

    safe_folder = "/".join(
        sanitize_storage_segment(part) for part in folder_path.split("/") if part
    )
    return f"{safe_folder}/{safe_name}"

