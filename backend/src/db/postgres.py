import os
import threading
from contextlib import contextmanager
from typing import Any, Iterable, Sequence

from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor, execute_values, Json
from psycopg2.pool import SimpleConnectionPool

try:
    from pgvector.psycopg2 import register_vector
except ImportError:  # pragma: no cover - optional during local tooling
    register_vector = None

load_dotenv()

_pool: SimpleConnectionPool | None = None
_pool_lock = threading.Lock()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                max_connections = int(os.getenv("DB_POOL_MAX", "5"))
                _pool = SimpleConnectionPool(
                    1,
                    max_connections,
                    dsn=get_database_url(),
                )
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    pool = get_pool()
    conn = pool.getconn()
    try:
        if register_vector is not None:
            register_vector(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def fetch_all(query: str, params: Sequence[Any] | None = None) -> list[dict]:
    with get_cursor() as cursor:
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def fetch_one(query: str, params: Sequence[Any] | None = None) -> dict | None:
    with get_cursor() as cursor:
        cursor.execute(query, params or ())
        row = cursor.fetchone()
        return dict(row) if row else None


def execute(query: str, params: Sequence[Any] | None = None) -> None:
    with get_cursor(commit=True) as cursor:
        cursor.execute(query, params or ())


def _adapt_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def _returning_clause(returning: str | Sequence[str] | None) -> sql.SQL | None:
    if returning is None:
        return None
    if returning == "*":
        return sql.SQL("*")
    if isinstance(returning, str):
        return sql.SQL(returning)
    return sql.SQL(", ").join(sql.Identifier(column) for column in returning)


def insert_row(
    table: str,
    row: dict[str, Any],
    returning: str | Sequence[str] | None = "*",
) -> dict | None:
    columns = list(row.keys())
    values = [_adapt_value(row[column]) for column in columns]
    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    returning_sql = _returning_clause(returning)
    if returning_sql is not None:
        query += sql.SQL(" RETURNING ") + returning_sql
    with get_cursor(commit=True) as cursor:
        cursor.execute(query, values)
        row = cursor.fetchone()
        return dict(row) if row else None


def bulk_insert_rows(
    table: str,
    rows: list[dict[str, Any]],
    returning: str | Sequence[str] | None = None,
) -> list[dict]:
    if not rows:
        return []

    columns = list(rows[0].keys())
    values = [
        tuple(_adapt_value(row.get(column)) for column in columns)
        for row in rows
    ]
    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES %s").format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    returning_sql = _returning_clause(returning)
    if returning_sql is not None:
        query += sql.SQL(" RETURNING ") + returning_sql

    with get_cursor(commit=True) as cursor:
        result = execute_values(
            cursor,
            query.as_string(cursor.connection),
            values,
            fetch=returning_sql is not None,
        )
        if returning_sql is None:
            return []
        return [dict(row) for row in (result or [])]


def update_row(
    table: str,
    row: dict[str, Any],
    where_clause: str,
    where_params: Sequence[Any],
    returning: str | Sequence[str] | None = "*",
) -> dict | None:
    columns = list(row.keys())
    values = [_adapt_value(row[column]) for column in columns]
    assignments = sql.SQL(", ").join(
        sql.SQL("{column} = %s").format(column=sql.Identifier(column))
        for column in columns
    )
    query = sql.SQL("UPDATE {table} SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE {where_clause}").format(
        table=sql.Identifier(table),
        assignments=assignments,
        where_clause=sql.SQL(where_clause),
    )
    returning_sql = _returning_clause(returning)
    if returning_sql is not None:
        query += sql.SQL(" RETURNING ") + returning_sql
    with get_cursor(commit=True) as cursor:
        cursor.execute(query, values + list(where_params))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_where(table: str, where_clause: str, where_params: Sequence[Any]) -> None:
    query = sql.SQL("DELETE FROM {table} WHERE {where_clause}").format(
        table=sql.Identifier(table),
        where_clause=sql.SQL(where_clause),
    )
    with get_cursor(commit=True) as cursor:
        cursor.execute(query, where_params)
