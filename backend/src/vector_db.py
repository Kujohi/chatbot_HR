"""Local vector-search smoke test.

The production path now uses PostgreSQL + pgvector through the retrieval
service. This file is kept as a lightweight manual entry point.
"""

from src.services.retrieval_service import search_document_summaries


if __name__ == "__main__":
    print(search_document_summaries("test query", limit=3))
