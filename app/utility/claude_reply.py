import tiktoken
from app.services.db import db

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
        sender = "You" if chat["sender"] == "human" else "AI"
        message = chat.get("message", "")
        messages.append(f"{sender}: {message.strip()}")

    recent_text = "\n".join(messages)
    print(f"🧾 Recent Conversation Chats:\n{recent_text}")
    return recent_text
