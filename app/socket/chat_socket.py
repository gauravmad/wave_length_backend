import random
from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from datetime import datetime
from app.services.claude import get_claude_reply
from app.socket.controller.chat_controller import fetch_chat_history,save_user_message
from app.memory.memory_service import MemoryService

def register_chat_events(socketio: SocketIO):
    print("SocketIO initialized:", socketio)
    chats = db.chats
    memory_service = MemoryService()

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

            # Save user message to database
            message_data = save_user_message(user_id, character_id, message)
            
            # Add user message to Mem0 memory
            memory_service.add_message_to_memory(user_id, character_id, message, "User")
            print(f"💾 User message added to Mem0 memory: {message[:50]}...")
            
            socketio.emit("message_sent", message_data, to=request.sid)

        except Exception as e:
            print(f"❌ Error saving user message: {e}")
            socketio.emit("message_error", {
                "error": "Failed to save user message"
            }, to=request.sid)


    # Gets Image Url saves in MongoDB
    @socketio.on("upload_image") 
    def handle_image_upload(data):
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        prompt = data.get("message","").strip()
        image_url = data.get("image_url")    

        if not all([user_id,character_id,character_name,image_url]):
            print("Missing required image message data")
            socketio.emit("message_error",{
                "error":"Missing UserId, CharacterId, CharacterName or Image"  
            }, to=request.sid)
            return
        
        try:
            if not prompt:
                fallback_prompts = [
                    "Please analyze this image and share your thoughts.",
                    "What do you observe in this image?",
                    "Give your insights based on the image.",
                    "Describe what’s happening in this picture.",
                    "What can you interpret from this image?"
                ]
                prompt = random.choice(fallback_prompts)
            print(f"Image Upload received from user {user_id}") 

            message_data = save_user_message(
                user_id=user_id,
                character_id=character_id,
                message=prompt,
                image_url=image_url
            )   

            # Emit message back to frontend
            socketio.emit("message_sent", {
                "userId": message_data["userId"],
                "characterId": message_data["characterId"],
                "sender": message_data["sender"],
                "message": message_data["message"],
                "timestamp": message_data["timestamp"],
                "image": message_data.get("image_url")
            }, to=request.sid)

        except Exception as e:
            print(f"❌ Error processing uploaded image: {e}")
            socketio.emit("message_error", {
                "error": "Failed to process uploaded image."
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
            if not prompt and image_url:
                fallback_prompts = [
                    "Please analyze this image and share your thoughts.",
                    "What do you observe in this image?",
                    "Give your insights based on the image.",
                    "Describe what's happening in this picture.",
                    "What can you interpret from this image?"
                ]
                prompt = random.choice(fallback_prompts)
                print(f"📷 Image Upload with no message - using fallback prompt for user {user_id}")

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
