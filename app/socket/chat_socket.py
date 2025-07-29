from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from app.services.claude import get_claude_reply

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
            # Use string format for consistency
            messages = chats.find({
                "userId": str(user_id),
                "characterId": str(character_id)
            }).sort("timestamp", 1)  # 1 for ascending order

            # Convert MongoDB cursor to list
            messages_list = [{
                "userId": message["userId"],
                "characterId": message["characterId"],
                "sender": message["sender"],
                "message": message["message"],
                "timestamp": message["timestamp"]
            } for message in messages]

            socketio.emit("receive_chat_history", {
                "messages": messages_list
            }, to=request.sid)
            print(f"📤 Sent {len(messages_list)} messages to client {request.sid}")

        except Exception as e:
            print(f"❌ Error fetching chat history: {e}")
            socketio.emit("chat_history_error", {
                "error": "Failed to fetch chat history"
            }, to=request.sid)

    @socketio.on("send_message")
    def handle_send_message(data):
        print(f"📨 Received message data: {data}")
        
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        message = data.get("message")

        # Validate required fields
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
            print(f"🚀 Calling get_claude_reply for user {user_id}")
            
            # Call Claude function which now handles ALL saving logic
            result = get_claude_reply(
                prompt=message,
                user_id=str(user_id),  # Ensure string format
                character_name=character_name,
                character_id=str(character_id)  # Ensure string format
            )

            print(f"✅ Claude function completed. Success: {result.get('success')}")

            if result.get("success"):
                # Emit successful AI response
                socketio.emit("receive_message", {
                    "userId": result["userId"],
                    "characterId": result["characterId"],
                    "sender": "ai",
                    "message": result["message"],
                    "timestamp": result["timestamp"]
                }, to=request.sid)
                print(f"📤 AI response sent to client {request.sid}")
            else:
                # Emit error response
                socketio.emit("receive_message", {
                    "userId": result["userId"],
                    "characterId": result["characterId"],
                    "sender": "ai",
                    "message": result["message"],
                    "timestamp": result["timestamp"]
                }, to=request.sid)
                print(f"📤 Error response sent to client {request.sid}")

        except Exception as e:
            print(f"❌ Socket handler error: {e}")
            import traceback
            traceback.print_exc()
            
            # Send generic error to client
            socketio.emit("message_error", {
                "error": "Internal server error"
            }, to=request.sid)