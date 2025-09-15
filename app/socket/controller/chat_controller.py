from datetime import datetime
from app.services.db import db
from app.memory.summary import update_summary_with_new_message
from typing import Optional

# Save User Message
def save_user_message(
    user_id: str, 
    character_id: str, 
    message: Optional[str] = None,  # Make message optional
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None
) -> dict:
    timestamp = datetime.utcnow().isoformat()
    message_data = {
        "userId": str(user_id),
        "characterId": str(character_id),
        "sender": "user",
        "timestamp": timestamp
    }

    # Add the appropriate field based on what's provided
    if image_url:
        message_data["image_url"] = image_url
    elif audio_url:
        message_data["audio_url"] = audio_url
    elif message:  # Only add message if it's provided and not None/empty
        message_data["message"] = message
    else:
        # If none of the content fields are provided, raise an error
        raise ValueError("At least one of message, image_url, or audio_url must be provided")

    result = db.chats.insert_one(message_data)
    message_data["_id"] = str(result.inserted_id)  # Convert ObjectId to string
    return message_data

# Save AI Message
def save_ai_message(
    user_id: str, 
    character_id: str, 
    message: str,
    image_url: Optional[str] = None
) -> dict:
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
def fetch_chat_history(
    user_id: str, 
    character_id: str,
    image_url: Optional[str] = None
) -> list:
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
        "audio_url": msg.get("audio_url"),  # Will be None if not present
        "timestamp": msg["timestamp"]
    } for msg in messages]

def update_conversation_summary(
    user_id: str, 
    character_id: str, 
    new_message: str,
    image_url: Optional[str] = None
) -> str:
    """Update conversation summary for a user and character."""
    return update_summary_with_new_message(
        user_id=user_id,
        character_id=character_id,
        new_message=new_message
    )