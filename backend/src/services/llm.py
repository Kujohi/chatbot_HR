import os
import asyncio
import datetime
from re import M
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Any, Dict, List, Union
from langchain_openai import ChatOpenAI
import logging
from src.utils.utils import setup_logging
setup_logging()
# from langchain_openrouter import ChatOpenRouter

logger = logging.getLogger(__name__)

load_dotenv()


def get_llm_client():
    client = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        # model="gemini-2.5-flash", 
        temperature=0,  # Gemini 3.0+ defaults to 1.0
    )
    # model="qwen/qwen3-32b",

    # client = ChatOpenAI(
    #     model="gpt-5.4-nano",
    #     temperature=0,
    # )
    # client = ChatGroq(
    #     model="openai/gpt-oss-20b",
    #     temperature=0,
    #     callbacks=callbacks
    # )

    return client

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


def chat_complete(messages):
    client = get_llm_client()
    logger.info("Chat complete for {}".format(messages))
    lc_messages = _to_langchain_messages(messages)
    return client.invoke(lc_messages).text.strip()

def chat_complete_with_structured(messages, model):
    client = get_llm_client()
    structured_client = client.with_structured_output(model)
    logger.info("Chat complete with structured output for {}".format(messages))

    return structured_client.invoke(messages)