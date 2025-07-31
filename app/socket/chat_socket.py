from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from datetime import datetime
from app.services.claude import get_claude_reply

def register_chat_events(socketio: SocketIO):
    print("SocketIO initialized:", socketio)
    chats = db.chats

    # Socket Connected 
    @socketio.on('connect')
    def handle_connect():
        print(f"Client connected: {request.sid}")


    # Socket Disconnected
    @socketio.on('disconnect')
    def handle_disconnect():
        print(f"Client disconnected: {request.sid}")

        
    # Socket to Fetch the chat history 
    @socketio.on("fetch_chat_history")
    def handle_fetch_chat_history(data):
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
            messages = chats.find({
                "userId": str(user_id),
                "characterId": str(character_id)
            }).sort("timestamp", 1)

            messages_list = [{
                "userId": msg["userId"],
                "characterId": msg["characterId"],
                "sender": msg["sender"],
                "message": msg["message"],
                "timestamp": msg["timestamp"]
            } for msg in messages]

            socketio.emit("receive_chat_history", {
                "messages": messages_list
            }, to=request.sid)

            print(f"📤 Sent {len(messages_list)} messages to client {request.sid}")

        except Exception as e:
            print(f"❌ Error fetching chat history: {e}")
            socketio.emit("chat_history_error", {
                "error": "Failed to fetch chat history"
            }, to=request.sid)


    # Socket Handle Send Message
    @socketio.on("send_message")
    def handle_send_message(data):
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        message = data.get("message")

        if not all([user_id, character_id, character_name, message]):
            print("❌ Missing required data:", {
                "user_id": bool(user_id),
                "character_id": bool(character_id),
                "character_name": bool(character_name),
                "message": bool(message)
            })
            socketio.emit("message_error", {
                "error": "Missing required fields"
            }, to=request.sid)
            return

        try:
            timestamp = datetime.utcnow().isoformat()

            # Saving the User Chat to MongoDB
            db.chats.insert_one({
                "userId": str(user_id),
                "characterId": str(character_id),
                "sender": "user",
                "message": message,
                "timestamp": timestamp
            })

            print(f"✅ User message saved for user {user_id}")
            socketio.emit("message_sent", {
                "userId": user_id,
                "characterId": character_id,
                "sender": "user",
                "message": message,
                "timestamp": timestamp
            }, to=request.sid)

        except Exception as e:
            print(f"❌ Error saving user message: {e}")
            socketio.emit("message_error", {
                "error": "Failed to save user message"
            }, to=request.sid)

            
    # Socket to Trigger AI Reply 
    @socketio.on("trigger_ai_reply")
    def handle_ai_reply(data):
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        prompt = data.get("message")

        try:
            print(f"🤖 AI reply triggered for user {user_id}")
            result = get_claude_reply(
                prompt=prompt,
                user_id=str(user_id),
                character_name=character_name,
                character_id=str(character_id)
            )

            socketio.emit("receive_message", {
                "userId": result["userId"],
                "characterId": result["characterId"],
                "sender": "ai",
                "message": result["message"],
                "timestamp": result["timestamp"]
            }, to=request.sid)

        except Exception as e:
            print(f"❌ AI reply error: {e}")
            socketio.emit("message_error", {
                "error": "Internal server error"
            }, to=request.sid)
