from __future__ import annotations

import logging

from src.services.conversation import (
    get_conversation_messages,
    update_chat_conversation,
)
from src.services.routing_service import bot_route_answer_message
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def _is_gemini_quota_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    message = str(exc)
    return status_code == 429 or "RESOURCE_EXHAUSTED" in message or "429" in message


def llm_handle_message(thread_id: str, message: str) -> dict[str, str]:
    """
    Main message handler with intelligent routing.

    Flow:
    1. Save user message to conversation history
    2. Load conversation context
    3. Route to appropriate handler (RAG or general chat)
    4. Generate and save response
    """
    logger.info("Start handling message")
    update_chat_conversation(thread_id, "user", message, True)
    logger.info("Conversation updated")

    messages = get_conversation_messages(thread_id)
    logger.info("Conversation messages: %s", messages)
    history = messages[:-1]

    try:
        response = bot_route_answer_message(history, message)
    except Exception as exc:
        if not _is_gemini_quota_error(exc):
            raise
        logger.warning("Gemini quota exhausted while handling thread %s", thread_id)
        response = (
            "Hệ thống AI đang tạm quá tải quota, nên mình chưa thể trả lời ngay lúc này. "
            "Bạn thử lại sau ít phút nhé."
        )

    logger.info("Chatbot response generated")

    update_chat_conversation(thread_id, "assistant", response, False)
    return {"role": "assistant", "content": response}
