from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from app.services.gemini import get_gemini_reply
from datetime import datetime

def register_chat_events(socketio: SocketIO):
    chat_collection = db.chats

    @socketio.on("send_message")
    def handle_send_message(data):
        user_id = data.get("userId")
        message = data.get("message")

        chat_collection.update_one(
            {"userId":user_id},
            {"$push":{
                "chatHistory":{
                    "sender":"user",
                    "message":message,
                    "timestamp":datetime.now().isoformat()
                }
            }},
            upsert=True
        )

        # Get Gemini AI reply
        ai_reply = get_gemini_reply(message, user_id)

        chat_collection.update_one(
            {"userId": user_id},
            {"$push": {
                "chatHistory": {
                    "sender": "ai",
                    "message": ai_reply,
                    "timestamp": datetime.now().isoformat()
                }
            }},
            upsert=True
        )

        socketio.emit("receive_message", {
            "userId": user_id,
            "message": ai_reply
        }, room= request.sid)