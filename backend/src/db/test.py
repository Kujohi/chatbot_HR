from src.db.postgres import fetch_one


if __name__ == "__main__":
    result = fetch_one("SELECT 1 AS ok")
    print(result)
