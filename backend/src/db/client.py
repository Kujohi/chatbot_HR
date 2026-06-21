from src.db.postgres import get_database_url, get_pool


def get_db_pool():
    return get_pool()


def get_db_dsn() -> str:
    return get_database_url()

