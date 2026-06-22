from __future__ import annotations

import logging
from typing import Dict, List, Union

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.services.gemini_config import GEMINI_CHAT_MODEL, GEMINI_UTILITY_MODEL
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()


def get_llm_client(model_name: str = GEMINI_CHAT_MODEL):
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,  # Gemini 3.0+ defaults to 1.0
    )


def _to_langchain_messages(messages: List[Union[Dict, SystemMessage, HumanMessage]]):
    converted = []
    for message in messages:
        if isinstance(message, (SystemMessage, HumanMessage)):
            converted.append(message)
            continue
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
    return converted


def chat_complete(messages, model_name: str = GEMINI_CHAT_MODEL):
    client = get_llm_client(model_name)
    logger.info("Chat complete for %s", messages)
    lc_messages = _to_langchain_messages(messages)
    return client.invoke(lc_messages).text.strip()


def chat_complete_with_structured(
    messages,
    model,
    model_name: str = GEMINI_UTILITY_MODEL,
):
    client = get_llm_client(model_name)
    structured_client = client.with_structured_output(model)
    logger.info("Chat complete with structured output for %s", messages)
    return structured_client.invoke(messages)
