from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from app.services.claude import get_claude_reply
from datetime import datetime

def register_chat_events(socketio: SocketIO):
    print("SocketIO initialized:", socketio)
    chats = db.chats

    @socketio.on('connect')
    def handle_connect():
        print(f"Client connected: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f"Client disconnected: {request.sid}")

    @socketio.on("fetch_chat_history")
    def handle_fetch_chat_history(data):
        print("Fetching chat history for:", data)
        user_id = data.get("userId")
        character_id = data.get("characterId")

        if not all([user_id, character_id]):
            print("Missing required data for chat history:", {
                "user_id": user_id,
                "character_id": character_id
            })
            socketio.emit("chat_history_error", {
                "error": "Missing userId or characterId"
            }, to=request.sid)
            return

        try:
            # Fetch messages sorted by timestamp
            messages = chats.find({
                "userId": user_id,
                "characterId": character_id
            }).sort("timestamp", 1)  # 1 for ascending order

            # Convert MongoDB cursor to list
            messages_list = [{
                "userId": message["userId"],
                "characterId": message["characterId"],
                "sender": message["sender"],
                "message": message["message"],
                "timestamp": message["timestamp"]
            } for message in messages]

            # Emit chat history back to the client
            socketio.emit("receive_chat_history", {
                "messages": messages_list
            }, to=request.sid)
            print(f"Sent {len(messages_list)} messages to client {request.sid}")
        except Exception as e:
            print(f"Error fetching chat history: {e}")
            socketio.emit("chat_history_error", {
                "error": "Failed to fetch chat history"
            }, to=request.sid)

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

            # Emit the response back to the client
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
            }, to=request.sid)