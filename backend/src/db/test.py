from src.db.postgres import fetch_one


result = fetch_one("SELECT 1 AS ok")
print(result)

