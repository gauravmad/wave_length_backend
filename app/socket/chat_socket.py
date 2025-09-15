import random
from flask_socketio import SocketIO
from flask import request
from app.services.db import db
from datetime import datetime
from app.services.claude import get_claude_reply
from app.socket.controller.chat_controller import fetch_chat_history,save_user_message
from app.memory.memory_service import MemoryService
from app.services.aws_bucket import handle_voice_upload
from app.routes.speech_to_text import transcribe_audio
import requests

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


    # Add this new SocketIO event handler to your chat_socket.py file:
    @socketio.on("save_voice_message")
    def handle_save_voice_message(data):
        try:
            user_id = data.get("userId")
            character_id = data.get("characterId")
            character_name = data.get("characterName")
            transcription = data.get("transcription")
            audio_url = data.get("audio_url")

            if not all([user_id, character_id, character_name, transcription]):
                raise ValueError("Missing required fields")

            transcribed_text = transcription.get("DisplayText", "")
            
            if not transcribed_text:
                socketio.emit("message_error", {
                    "error": "No transcribed text available"
                }, to=request.sid)
                return

            # Save the audio message with transcription
            message_data = save_user_message(
                user_id=user_id,
                character_id=character_id,
                message=transcribed_text,
                audio_url=audio_url
            )
            
            # Add to memory
            memory_service.add_message_to_memory(user_id, character_id, transcribed_text, "User")
            print(f"💾 Voice message added to Mem0 memory: {transcribed_text[:50]}...")

            # Emit confirmation back to frontend
            socketio.emit("voice_message_saved", {
                "userId": message_data["userId"],
                "characterId": message_data["characterId"],
                "sender": message_data["sender"],
                "message": message_data["message"],
                "timestamp": message_data["timestamp"],
                "audio_url": message_data.get("audio_url"),
                "transcription": transcription
            }, to=request.sid)

            print(f"✅ Voice message saved successfully")

        except Exception as e:
            print(f"❌ Error saving voice message: {e}")
            socketio.emit("message_error", {
                "error": "Failed to save voice message"
            }, to=request.sid)          

    # Socket Handle Audio Upload
    @socketio.on("upload_audio")
    def handle_audio_upload(data):
        user_id = data.get("userId")
        character_id = data.get("characterId")
        character_name = data.get("characterName")
        language = data.get("language", "en-IN")

        print(f"Audio Upload received from user {user_id}")
        print(f"Character ID: {character_id}")
        print(f"Character Name: {character_name}")
        print(f"Language: {language}")
        print(f"Data: {data}")

        if not all([user_id, character_id, character_name]):
            print("Missing required audio message data")
            socketio.emit("message_error", {
                "error": "Missing UserId, CharacterId, or CharacterName"
            }, to=request.sid)
            return

        try:
            print(f"🎤 Audio Upload received from user {user_id}")

            # Get audio file from request
            if 'audio' not in request.files:
                socketio.emit("message_error", {
                    "error": "No audio file provided"
                }, to=request.sid)
                return

            audio_file = request.files['audio']
            if audio_file.filename == '':
                socketio.emit("message_error", {
                    "error": "No audio file selected"
                }, to=request.sid)
                return

            # Transcribe the audio using Azure Speech Services directly from the input file
            from app.config import Config
            
            # Read the audio file data directly
            audio_file.seek(0)  # Reset file pointer to beginning
            audio_data = audio_file.read()
            
            headers = {
                'Ocp-Apim-Subscription-Key': Config.AZURE_SPEECH_TO_TEXT_API_KEY,
                'Content-Type': 'audio/wav'
            }
            
            api_url = f"{Config.AZURE_SPEECH_TO_TEXT_API_URL}?language={language}"
            print(f"API URL: {api_url}")
            
            azure_response = requests.post(
                api_url,
                headers=headers,
                data=audio_data,
                timeout=30
            )
            print(f"Azure Response: {azure_response}")

            if azure_response.status_code == 200:
                transcription_result = azure_response.json()
                transcribed_text = transcription_result.get("DisplayText", "")

                print(f"Transcribed Text: {transcribed_text}")

                if transcribed_text:
                    # Upload audio file to S3 for storage (after successful transcription)
                    try:
                        audio_file.seek(0)  # Reset file pointer for S3 upload
                        audio_url = handle_voice_upload(audio_file)
                        print(f"✅ Audio uploaded to S3: {audio_url}")
                    except Exception as e:
                        print(f"⚠️ Warning: Failed to upload audio to S3: {str(e)}")
                        audio_url = None  # Continue without S3 URL if upload fails

                    # Save the audio message with transcription
                    message_data = save_user_message(
                        user_id=user_id,
                        character_id=character_id,
                        message=transcribed_text,
                        audio_url=audio_url
                    )
                    print(f"Message Data: {message_data}")

                    # Add to memory
                    memory_service.add_message_to_memory(user_id, character_id, transcribed_text, "User")
                    print(f"💾 Audio message added to Mem0 memory: {transcribed_text[:50]}...")

                    # Emit user message back to frontend
                    socketio.emit("message_sent", {
                        "userId": message_data["userId"],
                        "characterId": message_data["characterId"],
                        "sender": message_data["sender"],
                        "message": message_data["message"],
                        "timestamp": message_data["timestamp"],
                        "audio_url": message_data.get("audio_url"),
                        "transcription": {
                            "RecognitionStatus": transcription_result.get("RecognitionStatus", "Success"),
                            "Offset": transcription_result.get("Offset", 0),
                            "Duration": transcription_result.get("Duration", 0),
                            "DisplayText": transcribed_text
                        }
                    }, to=request.sid)

                    # Automatically trigger AI reply with the transcribed text
                    print(f"🤖 Triggering AI reply for transcribed text: {transcribed_text[:50]}...")
                    
                    try:
                        ai_result = get_claude_reply(
                            prompt=transcribed_text,
                            user_id=str(user_id),
                            character_name=character_name,
                            character_id=str(character_id)
                        )

                        # Emit AI response
                        socketio.emit("receive_message", {
                            "userId": ai_result["userId"],
                            "characterId": ai_result["characterId"],
                            "sender": "ai",
                            "message": ai_result["message"],
                            "timestamp": ai_result["timestamp"]
                        }, to=request.sid)

                        print(f"✅ AI reply sent successfully")

                    except Exception as e:
                        print(f"❌ Error generating AI reply: {e}")
                        socketio.emit("message_error", {
                            "error": "Failed to generate AI response"
                        }, to=request.sid)

                else:
                    socketio.emit("message_error", {
                        "error": "No speech detected in audio file"
                    }, to=request.sid)
            else:
                socketio.emit("message_error", {
                    "error": f"Speech recognition failed: {azure_response.status_code}"
                }, to=request.sid)

        except Exception as e:
            print(f"❌ Error processing uploaded audio: {e}")
            socketio.emit("message_error", {
                "error": "Failed to process uploaded audio"
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
