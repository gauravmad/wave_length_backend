import random
from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from datetime import datetime
from app.services.claude import get_claude_reply
from app.socket.controller.chat_controller import fetch_chat_history,save_user_message,update_conversation_summary

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
        try:
            user_id = data.get("userId")
            character_id = data.get("characterId")
            messages_list = fetch_chat_history(user_id, character_id)

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
        
        try:
            user_id = data.get("userId")
            character_id = data.get("characterId")
            character_name = data.get("characterName")
            message = data.get("message")

            if not all([user_id, character_id, character_name, message]):
                raise ValueError("Missing required fields")

            message_data = save_user_message(user_id, character_id, message)
            socketio.emit("message_sent", message_data, to=request.sid)

        except Exception as e:
            print(f"❌ Error saving user message: {e}")
            socketio.emit("message_error", {
                "error": "Failed to save user message"
            }, to=request.sid)

    #Update/Create a Global Summary
    @socketio.on("summarize_message")
    def handle_summarize_message(data):
        try:
            user_id = data.get("userId")
            character_id = data.get("characterId")
            new_message = data.get("message")
            # ✅ Call summary updater
            
            if not all([user_id, character_id, new_message]):
                raise ValueError("Missing required summary fields")
                
            summary = update_conversation_summary(user_id, character_id, new_message)
            socketio.emit("summarize_message", {
                "userId": user_id,
                "characterId": character_id,
                "summary": summary or "No summary generated"
            }, to=request.sid)

        except Exception as e:
            print(f"❌ Error summarizing message: {e}")
            socketio.emit("summary_error", {
                "error": "Failed to summarize message."
            }, to=request.sid)

    # Socket to Trigger AI Reply 
    @socketio.on("trigger_ai_reply")
    def handle_ai_reply(data):
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        prompt = data.get("message")
        image_url = data.get("image_url")

        try:
            print(f"🤖 AI reply triggered for user {user_id}")
            result = get_claude_reply(
                prompt=prompt,
                user_id=str(user_id),
                character_name=character_name,
                character_id=str(character_id),
                image_url=image_url
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
