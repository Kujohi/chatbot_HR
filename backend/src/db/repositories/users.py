from psycopg2.extras import RealDictCursor

from src.db.postgres import fetch_one, get_cursor


def get_user_by_id(user_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, name, role, created_at, updated_at
        FROM users
        WHERE id = %s
        """,
        (str(user_id),),
    )


def upsert_user(user_id: str, name: str | None = None, role: str = "user") -> dict:
    cursor_ctx = get_cursor(commit=True)
    cursor = cursor_ctx.__enter__()
    row = None
    try:
        cursor.execute(
            """
            INSERT INTO users (id, name, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                role = EXCLUDED.role,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, name, role, created_at, updated_at
            """,
            (str(user_id), name, role),
        )
        row = cursor.fetchone()
    finally:
        cursor_ctx.__exit__(None, None, None)

    if row is None:
        raise RuntimeError("Failed to upsert user")
    return dict(row)
