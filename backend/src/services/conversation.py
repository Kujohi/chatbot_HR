from src.db.client import get_supabase
import logging
from src.utils.utils import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def format_conversation_messages(messages: list):
    formatted_messages = []
    for message in messages:
        role = message["role"]
        if role == "assistant":
            role = "ai"
        formatted_messages.append({
            "id": message.get("id"),
            "role": role,
            "content": message["content"],
            "created_at": message.get("created_at"),
        })
    return formatted_messages

def update_chat_conversation(thread_id: str, role: str, content: str, is_request: bool = True):
    logger.info(f"Update chat conversation for thread {thread_id} with role {role} and content {content}")
    supabase = get_supabase()
    return supabase.table("chat_conversations").insert({
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "is_request": is_request,
    }).execute()

def get_conversation_messages(thread_id: str):
    supabase = get_supabase()
    messages = (
        supabase.table("chat_conversations")
        .select("*")
        .eq("thread_id", thread_id)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
    )
    return format_conversation_messages(messages.data)

if __name__ == "__main__":
    # update_chat_conversation("00000000-0000-0000-0000-000000000000", "user", "test_message", True)
    print(get_conversation_messages("00000000-0000-0000-0000-000000000005"))