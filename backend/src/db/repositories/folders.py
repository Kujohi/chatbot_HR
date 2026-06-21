from src.db.postgres import delete_where, execute, fetch_all, fetch_one, insert_row


def get_folder_by_id(folder_id: int) -> dict | None:
    return fetch_one(
        """
        SELECT id, name, slug, path, parent_id, description, created_by, created_at, updated_at
        FROM document_folders
        WHERE id = %s
        """,
        (folder_id,),
    )


def get_folder_by_path(path: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, name, slug, path, parent_id, description, created_by, created_at, updated_at
        FROM document_folders
        WHERE path = %s
        LIMIT 1
        """,
        (path,),
    )


def list_folders(parent_id: int | None = None) -> list[dict]:
    if parent_id is None:
        return fetch_all(
            """
            SELECT id, name, slug, path, parent_id, description, created_by, created_at, updated_at
            FROM document_folders
            WHERE parent_id IS NULL
            ORDER BY name
            """
        )
    return fetch_all(
        """
        SELECT id, name, slug, path, parent_id, description, created_by, created_at, updated_at
        FROM document_folders
        WHERE parent_id = %s
        ORDER BY name
        """,
        (parent_id,),
    )


def list_all_folder_links() -> list[dict]:
    return fetch_all("SELECT id, parent_id FROM document_folders")


def list_all_document_folder_links() -> list[dict]:
    return fetch_all("SELECT id, folder_id FROM documents")


def get_or_create_folder(
    name: str,
    slug: str,
    path: str,
    parent_id: int | None,
    description: str = "",
    created_by: str = "",
) -> dict:
    existing = get_folder_by_path(path)
    if existing:
        return existing
    row = insert_row(
        "document_folders",
        {
            "name": name,
            "slug": slug,
            "path": path,
            "parent_id": parent_id,
            "description": description,
            "created_by": created_by,
        },
        returning="*",
    )
    if row is None:
        raise RuntimeError(f"Failed to create folder at path {path}")
    return row


def delete_folder(folder_id: int) -> None:
    delete_where("document_folders", "id = %s", (folder_id,))

