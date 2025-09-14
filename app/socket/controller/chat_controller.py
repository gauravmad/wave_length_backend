from datetime import datetime
from app.services.db import db
from app.memory.summary import update_summary_with_new_message
from typing import Optional

# Save User Message
def save_user_message(user_id:str, character_id:str, message:str, image_url:Optional[str] = None) -> dict:
    timestamp = datetime.utcnow().isoformat()
    message_data = {
        "userId":str(user_id),
        "characterId":str(character_id),
        "sender":"user",
        "timestamp": timestamp
    }

    if image_url:
        message_data["image_url"] = image_url
    else:
        message_data["message"] = message    

    result = db.chats.insert_one(message_data)
    message_data["_id"] = str(result.inserted_id)  # Convert ObjectId to string
    return message_data

# Save AI Message
def save_ai_message(user_id: str, character_id: str, message: str) -> dict:
    timestamp = datetime.utcnow().isoformat()
    message_data = {
        "userId": str(user_id),
        "characterId": str(character_id),
        "sender": "ai",
        "message": message,
        "timestamp": timestamp
    }
    db.chats.insert_one(message_data)
    return message_data

# Fetch Chat History
def fetch_chat_history(user_id: str, character_id: str) -> list:
    """Fetch chat history for a user and character."""
    if not all([user_id, character_id]):
        raise ValueError("Missing userId or characterId")
        
    messages = db.chats.find({
        "userId": str(user_id),
        "characterId": str(character_id)
    }).sort("timestamp", 1)
    
    return [{
        "userId": msg["userId"],
        "characterId": msg["characterId"],
        "sender": msg["sender"],
        "message": msg.get("message"),
        "image_url": msg.get("image_url"),  # Will be None if not present
        "timestamp": msg["timestamp"]
    } for msg in messages]

def update_conversation_summary(user_id: str, character_id: str, new_message: str) -> str:
    """Update conversation summary for a user and character."""
    return update_summary_with_new_message(
        user_id=user_id,
        character_id=character_id,
        new_message=new_message
    )