from flask import Blueprint, request, jsonify
import azure.cognitiveservices.speech as speechsdk
import os
import time
import tempfile
import io
from datetime import datetime
from werkzeug.datastructures import FileStorage
from app.config import Config
from app.services.aws_bucket import handle_speech_audio_upload
from app.socket.controller.chat_controller import save_ai_message
from app.memory.memory_service import MemoryService

# Create blueprint
text_to_speech_bp = Blueprint('text_to_speech', __name__)

def create_s3_audio_upload(audio_data, filename="tts_audio.wav"):
    """
    Create a FileStorage object from audio bytes for S3 upload
    
    Args:
        audio_data (bytes): Audio data in WAV format
        filename (str): Filename for the audio file
        
    Returns:
        FileStorage: File-like object for S3 upload
    """
    audio_file_obj = FileStorage(
        stream=io.BytesIO(audio_data),
        filename=filename,
        content_type='audio/wav'
    )
    return audio_file_obj

@text_to_speech_bp.route("/", methods=["POST"])
def synthesize_speech():
    """
    Text to speech endpoint that:
    1. Accepts text input with user_id and character_id
    2. Uses Azure Speech Services to convert text to speech
    3. Uploads generated audio to S3 in speech-audio folder
    4. Adds text to memory service
    5. Saves message to database with audio URL
    6. Returns the audio URL and synthesis details
    """
    start_time = time.time()
    request_id = f"tts_req_{int(time.time() * 1000)}"
    
    print(f"\n🔊 ===== TEXT-TO-SPEECH API REQUEST START =====")
    print(f"📋 Request ID: {request_id}")
    print(f"🕒 Timestamp: {datetime.now().isoformat()}")
    print(f"🌐 Client IP: {request.remote_addr}")
    print(f"📡 User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    
    try:
        # ✅ Get request data (JSON or form data)
        print(f"📝 Extracting request parameters...")
        if request.is_json:
            data = request.get_json()
            user_id = data.get("user_id")
            character_id = data.get("character_id")
            text = data.get("text")
            voice_name = data.get("voice_name", "en-IN-AartiIndicNeural")
            language = data.get("language", "en-IN")
        else:
            user_id = request.form.get("user_id")
            character_id = request.form.get("character_id")
            text = request.form.get("text")
            voice_name = request.form.get("voice_name", "en-IN-AartiIndicNeural")
            language = request.form.get("language", "en-IN")
        
        print(f"👤 User ID: {user_id}")
        print(f"🎭 Character ID: {character_id}")
        print(f"📝 Text: '{text[:100]}{'...' if len(text) > 100 else ''}'")
        print(f"🎤 Voice: {voice_name}")
        print(f"🌍 Language: {language}")

        # ✅ Validate required fields
        if not user_id or not character_id or not text:
            print(f"❌ Missing required fields - User ID: {bool(user_id)}, Character ID: {bool(character_id)}, Text: {bool(text)}")
            return jsonify({
                "error": "Missing required fields",
                "message": "user_id, character_id, and text are required"
            }), 400

        if len(text.strip()) == 0:
            print(f"❌ Empty text provided")
            return jsonify({
                "error": "Empty text",
                "message": "Text cannot be empty"
            }), 400

        # ✅ Configure Azure Speech Services
        print(f"🤖 Configuring Azure Speech Services...")
        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=Config.AZURE_TEXT_TO_SPEECH_API_KEY,
                region=Config.AZURE_TEXT_TO_SPEECH_REGION
            )
            speech_config.speech_synthesis_voice_name = voice_name
            
            print(f"🔑 Using Azure subscription key: {Config.AZURE_TEXT_TO_SPEECH_API_KEY[:10]}...")
            print(f"🌍 Using Azure region: {Config.AZURE_TEXT_TO_SPEECH_REGION}")
            print(f"🎤 Using voice: {voice_name}")
        except Exception as e:
            print(f"❌ Failed to configure Azure Speech Services: {str(e)}")
            return jsonify({
                "error": "Azure Speech Services configuration failed",
                "message": str(e)
            }), 500

        # ✅ Synthesize speech to memory stream
        print(f"🎵 Starting speech synthesis...")
        synthesis_start_time = time.time()
        
        try:
            # Create a pull audio output stream to get the audio data
            pull_stream = speechsdk.audio.PullAudioOutputStream()
            audio_config = speechsdk.audio.AudioOutputConfig(stream=pull_stream)
            speech_synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, 
                audio_config=audio_config
            )
            
            # Perform synthesis
            result = speech_synthesizer.speak_text_async(text).get()
            synthesis_time = time.time() - synthesis_start_time
            
            print(f"⏱️ Speech synthesis completed in {synthesis_time:.2f}s")
            print(f"📊 Synthesis result reason: {result.reason}")
            
        except Exception as e:
            print(f"❌ Speech synthesis failed: {str(e)}")
            return jsonify({
                "error": "Speech synthesis failed",
                "message": str(e)
            }), 500

        # ✅ Check synthesis result
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print(f"✅ Speech synthesized successfully for text length: {len(text)} characters")
            
            # Get audio data from the result
            audio_data = result.audio_data
            print(f"📊 Generated audio size: {len(audio_data)} bytes")
            
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"❌ Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print(f"📄 Error details: {cancellation_details.error_details}")
                return jsonify({
                    "error": "Speech synthesis canceled",
                    "message": f"Reason: {cancellation_details.reason}, Details: {cancellation_details.error_details}"
                }), 500
            else:
                return jsonify({
                    "error": "Speech synthesis canceled",
                    "message": f"Reason: {cancellation_details.reason}"
                }), 500
        else:
            print(f"❌ Unexpected synthesis result: {result.reason}")
            return jsonify({
                "error": "Unexpected synthesis result",
                "message": f"Result reason: {result.reason}"
            }), 500

        # ✅ Create filename for the audio file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        audio_filename = f"tts_{user_id}_{character_id}_{timestamp}.wav"
        
        # ✅ Upload audio to S3
        print(f"☁️ Starting S3 upload of synthesized audio...")
        s3_start_time = time.time()
        try:
            audio_file_obj = create_s3_audio_upload(audio_data, audio_filename)
            file_url = handle_speech_audio_upload(audio_file_obj)
            s3_upload_time = time.time() - s3_start_time
            print(f"✅ S3 upload successful in {s3_upload_time:.2f}s")
            print(f"🔗 S3 URL: {file_url}")
        except Exception as e:
            print(f"❌ S3 upload failed: {str(e)}")
            return jsonify({
                "error": "File upload failed",
                "message": str(e)
            }), 500

        # ✅ Add message to memory service
        print(f"🧠 Adding message to memory service...")
        memory_start_time = time.time()
        try:
            MemoryService().add_message_to_memory(
                user_id,
                character_id,
                text,
                "Assistant"  # This is an AI-generated response
            )
            memory_time = time.time() - memory_start_time
            print(f"✅ TTS message added to memory in {memory_time:.2f}s: {text[:50]}...")
        except Exception as e:
            print(f"⚠️ Memory service failed: {e}")

        # ✅ Save message to database (only audio URL, no text)
        print(f"💾 Saving TTS audio to database...")
        db_start_time = time.time()
        try:
            timestamp = datetime.utcnow().isoformat()
            message_data = {
                "userId": str(user_id),
                "characterId": str(character_id),
                "sender": "ai",
                "audio_url": file_url,  # Only save audio URL
                "timestamp": timestamp
            }
            
            from app.services.db import db
            result = db.chats.insert_one(message_data)
            message_data["_id"] = str(result.inserted_id)
            
            db_time = time.time() - db_start_time
            print(f"✅ TTS audio saved to database (audio_url only) in {db_time:.2f}s")
        except Exception as e:
            print(f"⚠️ Failed to save TTS audio: {e}")

        # ✅ Calculate total processing time
        total_time = time.time() - start_time
        print(f"🎯 Total processing time: {total_time:.2f}s")
        print(f"📊 Performance breakdown:")
        print(f"   - Speech Synthesis: {synthesis_time:.2f}s")
        print(f"   - S3 Upload: {s3_upload_time:.2f}s")
        print(f"   - Memory Service: {memory_time:.2f}s")
        print(f"   - Database Save: {db_time:.2f}s")

        # ✅ Final API response
        response_data = {
            "success": True,
            "message": "Text-to-speech conversion completed successfully",
            "text": text,
            "audio_url": file_url,
            "voice_name": voice_name,
            "language": language,
            "audio_size_bytes": len(audio_data),
            "synthesis_time_seconds": round(synthesis_time, 2),
            "total_time_seconds": round(total_time, 2)
        }
        print(f"📤 Sending response: {response_data}")
        print(f"🔊 ===== TEXT-TO-SPEECH API REQUEST COMPLETED =====\n")
        
        return jsonify(response_data), 200

    except Exception as e:
        total_time = time.time() - start_time
        print(f"💥 Unexpected error occurred: {str(e)}")
        print(f"⏱️ Failed after: {total_time:.2f}s")
        print(f"🔊 ===== TEXT-TO-SPEECH API REQUEST ERROR =====\n")
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500
