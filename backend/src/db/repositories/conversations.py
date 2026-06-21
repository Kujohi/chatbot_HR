from src.db.postgres import execute, fetch_all, insert_row


def insert_conversation_message(
    thread_id: str,
    role: str,
    content: str,
    is_request: bool = True,
    completed: bool = False,
) -> dict:
    row = insert_row(
        "chat_conversations",
        {
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "is_request": is_request,
            "completed": completed,
        },
        returning="*",
    )
    if row is None:
        raise RuntimeError("Failed to insert conversation message")
    return row


def list_conversation_messages(thread_id: str) -> list[dict]:
    return fetch_all(
        """
        SELECT id, thread_id, role, content, is_request, completed, created_at, updated_at
        FROM chat_conversations
        WHERE thread_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (thread_id,),
    )

