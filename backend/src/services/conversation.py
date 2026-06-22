from __future__ import annotations

import logging

from src.db.repositories.conversations import (
    insert_conversation_message,
    list_conversation_messages as repo_list_conversation_messages,
)
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def format_conversation_messages(messages: list[dict]) -> list[dict]:
    formatted_messages = []
    for message in messages:
        role = "ai" if message["role"] == "assistant" else message["role"]
        formatted_messages.append(
            {
                "id": message.get("id"),
                "role": role,
                "content": message["content"],
                "created_at": message.get("created_at"),
            }
        )
    return formatted_messages


def update_chat_conversation(thread_id: str, role: str, content: str, is_request: bool = True):
    logger.info(
        "Update chat conversation for thread %s with role %s and content %s",
        thread_id,
        role,
        content,
    )
    return insert_conversation_message(thread_id, role, content, is_request=is_request)


def get_conversation_messages(thread_id: str):
    messages = repo_list_conversation_messages(thread_id)
    return format_conversation_messages(messages)
