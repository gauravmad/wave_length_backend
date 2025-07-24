from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from app.services.claude import get_claude_reply
from datetime import datetime

def register_chat_events(socketio: SocketIO):
    print("SocketIO", socketio)
    chats = db.chats

    @socketio.on("send_message")
    def handle_send_message(data):

        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        message = data.get("message")

        if not all([user_id, character_id, message]):
            print("Missing required data:", {
                "user_id": user_id,
                "character_id": character_id,
                "message": bool(message)
            })
            return

        # Store user message
        chat_doc = {
            "userId": user_id,
            "characterId": character_id,
            "sender": "user",
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        chats.insert_one(chat_doc)

        try:
            # Fix: Pass all 4 required parameters including character_id
            ai_reply = get_claude_reply(message, user_id, character_name, character_id)
            
            # Store AI response
            ai_doc = {
                "userId": user_id,
                "characterId": character_id,
                "sender": "ai",
                "message": ai_reply,
                "timestamp": datetime.utcnow().isoformat()
            }
            chats.insert_one(ai_doc)

            # Emit the response back to the 
            socketio.emit("receive_message", {
                "userId": user_id,
                "characterId": character_id,
                "sender": "ai",
                "message": ai_reply,
                "timestamp": datetime.utcnow().isoformat()
            }, to=request.sid)
            
        except Exception as e:
            print(f"Error getting Claude reply: {e}")
            error_message = "⚠️ Sorry, I'm having trouble responding right now."
            
            # Store error message
            error_doc = {
                "userId": user_id,
                "characterId": character_id,
                "sender": "ai",
                "message": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }
            chats.insert_one(error_doc)
            
            # Emit error response
            socketio.emit("receive_message", {
                "userId": user_id,
                "characterId": character_id,
                "sender": "ai",
                "message": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }, room=request.sid)