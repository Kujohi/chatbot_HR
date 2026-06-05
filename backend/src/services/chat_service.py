import logging
from src.services.conversation import update_chat_conversation, get_conversation_messages
from src.services.llm import chat_complete
from src.services.routing_service import bot_route_answer_message
from src.utils.utils import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

def llm_handle_message(thread_id, message):
    """
    Main message handler with intelligent routing.

    Flow:
    1. Save user message to conversation history
    2. Load conversation context
    3. Route to appropriate handler (RAG or general chat)
    4. Generate and save response
    """
    logger.info("Start handle message")

    # Update chat conversation
    update_chat_conversation(thread_id, "user", message, True)
    logger.info("Conversation updated")

    # Convert history to list messages
    messages = get_conversation_messages(thread_id)
    logger.info("Conversation messages: %s", messages)
    history = messages[:-1]

    # Use intelligent routing to handle the question
    # This will automatically choose between RAG, web search, or general chat
    response = bot_route_answer_message(history, message)
    logger.info(f"Chatbot response generated")

    # Save response to history
    update_chat_conversation(thread_id, "assistant", response, False)

    # Return full response
    return {"role": "assistant", "content": response}

if __name__ == "__main__":
    print(llm_handle_message("00000000-0000-0000-0000-000000000005", "9 giờ có được không?"))