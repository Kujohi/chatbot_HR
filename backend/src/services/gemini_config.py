from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash")
GEMINI_UTILITY_MODEL = os.getenv("GEMINI_UTILITY_MODEL", "gemini-2.5-flash-lite")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
