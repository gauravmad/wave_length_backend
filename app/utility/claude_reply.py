import tiktoken
from app.services.db import db
from datetime import datetime

# ------------------------- Token Counter ------------------------- #
def claude_token_count(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

# ------------------------- Global Summary Fetcher ------------------------- #
def fetch_global_summary(user_id: str, character_id: str) -> str:
    try:
        summary_doc = db.summaries.find_one({
            "userId": user_id,
            "characterId": character_id
        })
        
        if summary_doc and summary_doc.get("summary"):
            return summary_doc["summary"]
        return ""
    except Exception as e:
        print(f"Error fetching global summary: {e}")
        return ""

# ------------------------- Fetch Recent Chats ------------------------- #
def fetch_recent_chats(user_id: str, character_id: str, limit: int = 20) -> str:
    try:
        # Query for recent chats
        chat_cursor = db.chats.find(
            {"userId": str(user_id), "characterId": str(character_id)}
        ).sort("timestamp", -1).limit(limit)

        chat_docs = list(chat_cursor)
        
        # Handle case where no chats exist
        if not chat_docs:
            return "No previous messages found."

        messages = []
        for chat in reversed(chat_docs):  # Reverse to get chronological order
            sender = chat.get("sender")
            message = chat.get("message", "").strip()
            
            if not message:  # Skip empty messages
                continue

            # Format timestamp
            if "timestamp" in chat and isinstance(chat["timestamp"], datetime):
                time_str = chat["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                # Format message for Claude
                messages.append(f"[{time_str}] {sender}: {message}")
            else:
                # Skip messages without valid timestamps
                continue

        return "\n".join(messages) if messages else "No valid messages found."
        
    except Exception as e:
        print(f"Error fetching recent chats: {e}")
        return "Error retrieving chat history."