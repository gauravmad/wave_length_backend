from flask import Blueprint, request, jsonify
import requests
from app.config import Config
from app.services.aws_bucket import handle_voice_upload
from app.socket.controller.chat_controller import save_user_message
from app.memory.memory_service import MemoryService

# Create blueprint
speech_to_text_bp = Blueprint('speech_to_text', __name__)

@speech_to_text_bp.route("/", methods=["POST"])
def transcribe_audio():
    """
    Speech to text endpoint that:
    1. Accepts audio file upload (multipart/form-data)
    2. Uploads to S3 in voice-notes folder
    3. Uses Azure Speech Services for transcription
    4. Adds transcribed text to memory service
    5. Saves user message (only audio_url, not text)
    6. Returns the transcribed text + file URL
    """
    try:
        # ✅ Check if file is present in request
        if 'audio' not in request.files:
            return jsonify({
                "error": "No audio file provided",
                "message": "Please provide an audio file with key 'audio'"
            }), 400
        
        file = request.files['audio']

        if file.filename == '':
            return jsonify({
                "error": "No file selected",
                "message": "Please select an audio file to upload"
            }), 400

        # ✅ Get JSON body parameters
        user_id = request.form.get("user_id")
        character_id = request.form.get("character_id")
        language = request.form.get("language", "en-IN")

        if not user_id or not character_id:
            return jsonify({
                "error": "Missing required fields",
                "message": "Both user_id and character_id are required"
            }), 400

        # ✅ Upload file to S3
        try:
            file_url = handle_voice_upload(file)
        except Exception as e:
            return jsonify({
                "error": "File upload failed",
                "message": str(e)
            }), 500

        # ✅ Download file back from S3 for Azure Speech
        try:
            response = requests.get(file_url)
            response.raise_for_status()
            audio_data = response.content
        except Exception as e:
            return jsonify({
                "error": "Failed to download audio file",
                "message": str(e)
            }), 500

        # ✅ Prepare Azure request
        headers = {
            'Ocp-Apim-Subscription-Key': Config.AZURE_SPEECH_TO_TEXT_API_KEY,
            'Content-Type': 'audio/wav'
        }
        api_url = f"{Config.AZURE_SPEECH_TO_TEXT_API_URL}?language={language}"

        try:
            azure_response = requests.post(
                api_url,
                headers=headers,
                data=audio_data,
                timeout=60
            )

            if azure_response.status_code == 200:
                result = azure_response.json()
                transcribed_text = result.get("DisplayText", "")
                recognition_status = result.get("RecognitionStatus", "Success")
                offset = result.get("Offset", 0)
                duration = result.get("Duration", 0)

                # ✅ Step 1: Add message to memory
                try:
                    MemoryService().add_message_to_memory(
                        user_id,
                        character_id,
                        transcribed_text,
                        "User"
                    )
                    print(f"💾 Voice message added to memory: {transcribed_text[:50]}...")
                except Exception as e:
                    print(f"⚠️ Memory service failed: {e}")

                # ✅ Step 2: Save user message with ONLY audio_url
                try:
                    save_user_message(
                        user_id=user_id,
                        character_id=character_id,
                        audio_url=file_url   # only audio
                    )
                    print("💾 User message saved with audio_url only.")
                except Exception as e:
                    print(f"⚠️ Failed to save user message: {e}")

                # ✅ Final API response
                return jsonify({
                    "RecognitionStatus": recognition_status,
                    "Offset": offset,
                    "Duration": duration,
                    "DisplayText": transcribed_text,
                    "file_url": file_url
                }), 200

            else:
                return jsonify({
                    "error": "Azure Speech Services error",
                    "message": f"Status: {azure_response.status_code}, Response: {azure_response.text}"
                }), 500

        except requests.exceptions.Timeout:
            return jsonify({
                "error": "Request timeout",
                "message": "Azure Speech Services request timed out"
            }), 504
        except requests.exceptions.RequestException as e:
            return jsonify({
                "error": "Azure Speech Services request failed",
                "message": str(e)
            }), 500

    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500