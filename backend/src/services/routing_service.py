from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from src.services.llm import chat_complete, chat_complete_with_structured
from src.services.rag_service import bot_rag_answer_message
from src.services.rewriter import summarized_question

logger = logging.getLogger(__name__)


class RouteModel(BaseModel):
    route: Literal["hr_rag", "general_chat"] = Field(
        description="Choose exactly one route"
    )


def detect_route(standalone_question: str) -> str:
    """
    Detect the appropriate tool/route for handling the user's query.
    Enhanced for HR chatbot with 2 routing options.

    Routes:
    - hr_rag: Questions about HR, regulations (uses RAG system with vector search)
    - general_chat: Greetings, small talk, off-topic conversations, or answered questions.
    """
    logger.info("Detect route for %s", standalone_question)
    system_prompt = """Bạn là hệ thống định tuyến thông minh cho chatbot tư vấn nhân sự. Phân tích câu hỏi và chọn route phù hợp nhất:
    1. Nếu câu hỏi liên quan đến quy định công ty Menas, vấn đề về hành chính, nhân sự thì chọn route hr_rag.
    2. Nếu câu hỏi không liên quan đến quy định công ty Menas thì chọn route general_chat."""

    result = chat_complete_with_structured(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": standalone_question},
        ],
        RouteModel,
    )
    logger.info("Route result: %s", result)
    return result.route


def bot_route_answer_message(history, question: str):
    """
    Route user query to appropriate handler based on intent detection.

    Routes:
    - hr_rag: Use RAG system for hr questions
    - general_chat: Handle with simple conversation
    """
    standalone_question = summarized_question(history, question)
    route = detect_route(standalone_question)

    if route == "hr_rag":
        logger.info("Using RAG system for hr knowledge retrieval")
        return bot_rag_answer_message(standalone_question)

    logger.info("Using general chat system for general questions")
    system_prompt = """Bạn là trợ lý AI thân thiện giải đáp các câu hỏi về tài liệu liên quan đến chính sách của công ty Menas."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": standalone_question},
    ]
    return chat_complete(messages)
