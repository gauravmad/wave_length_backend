import tiktoken
from app.services.db import db
from datetime import datetime

# ------------------------- Token Counter ------------------------- #
def claude_token_count(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

# ------------------------- Global Summary Fetcher ------------------------- #
def fetch_global_summary(user_id: str, character_id: str) -> str:
    summary_doc = db.summaries.find_one({
        "userId": user_id,
        "characterId": character_id
    })
    
    if summary_doc and summary_doc.get("summary"):
        return summary_doc["summary"]
    return ""

# ------------------------- Fetch Recent Chats ------------------------- #
def fetch_recent_chats(user_id: str, character_id: str, limit: int = 20) -> str:
    chat_cursor = db.chats.find(
        {"userId": str(user_id), "characterId": str(character_id)}
    ).sort("timestamp", -1).limit(limit)

    chat_docs = list(chat_cursor)

    messages = []
    for chat in reversed(chat_docs):
        sender = "human" if chat["sender"] == "human" else "ai"
        message = chat.get("message", "").strip()

        if "timestamp" in chat and isinstance(chat["timestamp"], datetime):
            time_str = chat["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = "Unknown time"

        # For Claude → keep timestamps & sender
        messages.append(f"[{time_str}] {sender}: {message}")

    return "\n".join(messages)

