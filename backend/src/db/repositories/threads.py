from src.db.postgres import delete_where, fetch_all, fetch_one, insert_row


def get_thread_by_id(thread_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM threads
        WHERE id = %s
        """,
        (thread_id,),
    )


def list_threads_by_user(user_id: str) -> list[dict]:
    return fetch_all(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM threads
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (str(user_id),),
    )


def insert_thread(thread_id: str, user_id: str, title: str) -> dict:
    row = insert_row(
        "threads",
        {
            "id": thread_id,
            "user_id": str(user_id),
            "title": title,
        },
        returning="*",
    )
    if row is None:
        raise RuntimeError("Failed to insert thread")
    return row


def delete_thread(thread_id: str) -> None:
    delete_where("threads", "id = %s", (thread_id,))

