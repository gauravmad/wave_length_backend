from flask import Blueprint, request, jsonify
import requests
import os
import time
import tempfile
import subprocess
from datetime import datetime
from app.config import Config
from app.services.aws_bucket import handle_voice_upload
from app.socket.controller.chat_controller import save_user_message
from app.memory.memory_service import MemoryService

# Create blueprint
speech_to_text_bp = Blueprint('speech_to_text', __name__)

def convert_opus_to_wav(opus_data):
    """
    Convert Opus audio data to WAV format using FFmpeg
    
    Args:
        opus_data (bytes): Raw Opus audio data
        
    Returns:
        bytes: WAV audio data
        
    Raises:
        Exception: If conversion fails
    """
    print(f"🔄 Starting Opus to WAV conversion...")
    conversion_start_time = time.time()
    
    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix='.opus', delete=False) as opus_temp:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_temp:
            try:
                # Write opus data to temporary file
                opus_temp.write(opus_data)
                opus_temp.flush()
                opus_temp_path = opus_temp.name
                wav_temp_path = wav_temp.name
                
                print(f"📁 Temporary Opus file: {opus_temp_path}")
                print(f"📁 Temporary WAV file: {wav_temp_path}")
                
                # FFmpeg command to convert Opus to WAV
                # Using specific parameters for Azure Speech Services compatibility
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', opus_temp_path,           # Input Opus file
                    '-ar', '16000',                 # Sample rate: 16kHz (recommended for speech)
                    '-ac', '1',                     # Mono channel
                    '-sample_fmt', 's16',           # 16-bit signed integer
                    '-f', 'wav',                    # Output format WAV
                    '-y',                           # Overwrite output file
                    wav_temp_path                   # Output WAV file
                ]
                
                print(f"🎵 FFmpeg command: {' '.join(ffmpeg_cmd)}")
                
                # Execute FFmpeg conversion
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30  # 30 second timeout
                )
                
                if result.returncode != 0:
                    print(f"❌ FFmpeg conversion failed!")
                    print(f"📤 FFmpeg stdout: {result.stdout}")
                    print(f"📥 FFmpeg stderr: {result.stderr}")
                    raise Exception(f"FFmpeg conversion failed: {result.stderr}")
                
                # Read converted WAV data
                with open(wav_temp_path, 'rb') as wav_file:
                    wav_data = wav_file.read()
                
                conversion_time = time.time() - conversion_start_time
                print(f"✅ Opus to WAV conversion successful in {conversion_time:.2f}s")
                print(f"📊 Original Opus size: {len(opus_data)} bytes")
                print(f"📊 Converted WAV size: {len(wav_data)} bytes")
                
                return wav_data
                
            except subprocess.TimeoutExpired:
                print(f"⏰ FFmpeg conversion timed out")
                raise Exception("Audio conversion timed out")
            except FileNotFoundError:
                print(f"❌ FFmpeg not found. Please install FFmpeg")
                raise Exception("FFmpeg not installed. Please install FFmpeg to convert audio files.")
            except Exception as e:
                print(f"❌ Conversion error: {str(e)}")
                raise Exception(f"Audio conversion failed: {str(e)}")
            finally:
                # Clean up temporary files
                try:
                    if os.path.exists(opus_temp_path):
                        os.unlink(opus_temp_path)
                        print(f"🗑️ Cleaned up temporary Opus file")
                    if os.path.exists(wav_temp_path):
                        os.unlink(wav_temp_path)
                        print(f"🗑️ Cleaned up temporary WAV file")
                except Exception as cleanup_error:
                    print(f"⚠️ Failed to clean up temporary files: {cleanup_error}")

def detect_audio_format(file_data):
    """
    Detect audio format based on file header/magic bytes
    
    Args:
        file_data (bytes): Audio file data
        
    Returns:
        str: Detected format ('opus', 'wav', 'mp3', 'unknown')
    """
    if len(file_data) < 12:
        return 'unknown'
    
    # Check for different audio formats by magic bytes
    if file_data.startswith(b'OggS'):
        # Check if it's Opus in Ogg container
        if b'OpusHead' in file_data[:100]:
            return 'opus'
        return 'ogg'
    elif file_data.startswith(b'RIFF') and file_data[8:12] == b'WAVE':
        return 'wav'
    elif file_data.startswith(b'ID3') or file_data.startswith(b'\xff\xfb'):
        return 'mp3'
    elif file_data.startswith(b'\xff\xf1') or file_data.startswith(b'\xff\xf9'):
        return 'aac'
    else:
        return 'unknown'

@speech_to_text_bp.route("/", methods=["POST"])
def transcribe_audio():
    """
    Speech to text endpoint that:
    1. Accepts audio file upload (multipart/form-data)
    2. Uploads to S3 in voice-notes folder
    3. Detects audio format and converts Opus to WAV if needed
    4. Uses Azure Speech Services for transcription
    5. Adds transcribed text to memory service
    6. Saves user message (only audio_url, not text)
    7. Returns the transcribed text + file URL
    """
    start_time = time.time()
    request_id = f"req_{int(time.time() * 1000)}"
    
    print(f"\n🎤 ===== SPEECH-TO-TEXT API REQUEST START =====")
    print(f"📋 Request ID: {request_id}")
    print(f"🕒 Timestamp: {datetime.now().isoformat()}")
    print(f"🌐 Client IP: {request.remote_addr}")
    print(f"📡 User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    
    try:
        # ✅ Check if file is present in request
        print(f"📁 Checking for audio file in request...")
        if 'audio' not in request.files:
            print(f"❌ No audio file found in request")
            return jsonify({
                "error": "No audio file provided",
                "message": "Please provide an audio file with key 'audio'"
            }), 400
        
        file = request.files['audio']
        print(f"📄 Audio file found: {file.filename}")

        if file.filename == '':
            print(f"❌ Empty filename provided")
            return jsonify({
                "error": "No file selected",
                "message": "Please select an audio file to upload"
            }), 400

        # ✅ Get form parameters
        print(f"📝 Extracting form parameters...")
        user_id = request.form.get("user_id")
        character_id = request.form.get("character_id")
        language = request.form.get("language", "en-IN")
        
        print(f"👤 User ID: {user_id}")
        print(f"🎭 Character ID: {character_id}")
        print(f"🌍 Language: {language}")

        if not user_id or not character_id:
            print(f"❌ Missing required fields - User ID: {bool(user_id)}, Character ID: {bool(character_id)}")
            return jsonify({
                "error": "Missing required fields",
                "message": "Both user_id and character_id are required"
            }), 400

        # ✅ Read original file data
        print(f"📁 Reading original file data...")
        try:
            file.seek(0)  # Reset file pointer to beginning
            original_audio_data = file.read()
            print(f"📊 Original audio data size: {len(original_audio_data)} bytes")
        except Exception as e:
            print(f"❌ Failed to read original file: {str(e)}")
            return jsonify({
                "error": "Failed to read audio file",
                "message": str(e)
            }), 500

        # ✅ Detect audio format and convert if necessary
        print(f"🔍 Detecting audio format...")
        detected_format = detect_audio_format(original_audio_data)
        print(f"🎵 Detected audio format: {detected_format}")
        
        conversion_time = 0
        audio_data_for_upload = original_audio_data  # Default to original data
        final_filename = file.filename  # Default to original filename
        
        if detected_format == 'opus':
            print(f"🔄 Opus format detected - conversion to WAV required")
            try:
                conversion_start = time.time()
                audio_data_for_upload = convert_opus_to_wav(original_audio_data)
                conversion_time = time.time() - conversion_start
                content_type = 'audio/wav'
                # Change filename extension to .wav
                base_name = os.path.splitext(file.filename)[0]
                final_filename = f"{base_name}.wav"
                print(f"✅ Audio converted from Opus to WAV")
                print(f"📝 Final filename will be: {final_filename}")
            except Exception as e:
                print(f"❌ Audio conversion failed: {str(e)}")
                return jsonify({
                    "error": "Audio conversion failed",
                    "message": f"Failed to convert Opus to WAV: {str(e)}"
                }), 500
        elif detected_format == 'wav':
            print(f"✅ WAV format detected - no conversion needed")
            content_type = 'audio/wav'
        else:
            print(f"⚠️ Unsupported or unknown audio format: {detected_format}")
            # Try to convert anyway using FFmpeg (it supports many formats)
            try:
                print(f"🔄 Attempting conversion to WAV...")
                conversion_start = time.time()
                audio_data_for_upload = convert_opus_to_wav(original_audio_data)
                conversion_time = time.time() - conversion_start
                content_type = 'audio/wav'
                # Change filename extension to .wav
                base_name = os.path.splitext(file.filename)[0]
                final_filename = f"{base_name}.wav"
                print(f"✅ Audio converted to WAV successfully")
                print(f"📝 Final filename will be: {final_filename}")
            except Exception as e:
                print(f"❌ Audio conversion failed: {str(e)}")
                return jsonify({
                    "error": "Unsupported audio format",
                    "message": f"Detected format: {detected_format}. Conversion failed: {str(e)}"
                }), 400

        # ✅ Upload the final audio file (WAV format) to S3
        print(f"☁️ Starting S3 upload of final audio file...")
        s3_start_time = time.time()
        try:
            # Create a temporary file-like object with the converted audio data
            import io
            from werkzeug.datastructures import FileStorage
            
            audio_file_obj = FileStorage(
                stream=io.BytesIO(audio_data_for_upload),
                filename=final_filename,
                content_type=content_type
            )
            
            file_url = handle_voice_upload(audio_file_obj)
            s3_upload_time = time.time() - s3_start_time
            print(f"✅ S3 upload successful in {s3_upload_time:.2f}s")
            print(f"🔗 S3 URL: {file_url}")
        except Exception as e:
            print(f"❌ S3 upload failed: {str(e)}")
            return jsonify({
                "error": "File upload failed",
                "message": str(e)
            }), 500

        # ✅ Use the same audio data for Azure processing
        audio_data_for_azure = audio_data_for_upload

        # ✅ Prepare Azure request
        print(f"🤖 Preparing Azure Speech Services request...")
        headers = {
            'Ocp-Apim-Subscription-Key': Config.AZURE_SPEECH_TO_TEXT_API_KEY,
            'Content-Type': 'audio/wav'  # Always WAV now since we convert everything to WAV
        }
        api_url = f"{Config.AZURE_SPEECH_TO_TEXT_API_URL}?language={language}"
        
        print(f"🔗 Azure API URL: {api_url}")
        print(f"🔑 Using Azure subscription key: {Config.AZURE_SPEECH_TO_TEXT_API_KEY[:10]}...")
        print(f"📤 Sending {len(audio_data_for_azure)} bytes to Azure Speech Services...")
        print(f"🎵 Content-Type: audio/wav")

        azure_start_time = time.time()
        try:
            azure_response = requests.post(
                api_url,
                headers=headers,
                data=audio_data_for_azure,
                timeout=60
            )
            azure_processing_time = time.time() - azure_start_time
            print(f"⏱️ Azure processing completed in {azure_processing_time:.2f}s")
            print(f"📊 Azure response status: {azure_response.status_code}")

            if azure_response.status_code == 200:
                result = azure_response.json()
                transcribed_text = result.get("DisplayText", "")
                recognition_status = result.get("RecognitionStatus", "Success")
                offset = result.get("Offset", 0)
                duration = result.get("Duration", 0)
                
                print(f"✅ Azure transcription successful!")
                print(f"📝 Recognition Status: {recognition_status}")
                print(f"📄 Transcribed Text: '{transcribed_text}'")
                print(f"⏱️ Audio Duration: {duration} microseconds")
                print(f"📍 Audio Offset: {offset} microseconds")

                # ✅ Step 1: Add message to memory
                print(f"🧠 Adding message to memory service...")
                memory_start_time = time.time()
                try:
                    MemoryService().add_message_to_memory(
                        user_id,
                        character_id,
                        transcribed_text,
                        "User"
                    )
                    memory_time = time.time() - memory_start_time
                    print(f"✅ Voice message added to memory in {memory_time:.2f}s: {transcribed_text[:50]}...")
                except Exception as e:
                    print(f"⚠️ Memory service failed: {e}")

                # ✅ Step 2: Save user message with ONLY audio_url
                print(f"💾 Saving user message to database...")
                db_start_time = time.time()
                try:
                    save_user_message(
                        user_id=user_id,
                        character_id=character_id,
                        message="",
                        audio_url=file_url   # only audio
                    )
                    db_time = time.time() - db_start_time
                    print(f"✅ User message saved with audio_url only in {db_time:.2f}s.")
                except Exception as e:
                    print(f"⚠️ Failed to save user message: {e}")

                # ✅ Calculate total processing time
                total_time = time.time() - start_time
                print(f"🎯 Total processing time: {total_time:.2f}s")
                print(f"📊 Performance breakdown:")
                if conversion_time > 0:
                    print(f"   - Audio Conversion: {conversion_time:.2f}s")
                print(f"   - S3 Upload (WAV): {s3_upload_time:.2f}s")
                print(f"   - Azure Processing: {azure_processing_time:.2f}s")
                print(f"   - Memory Service: {memory_time:.2f}s")
                print(f"   - Database Save: {db_time:.2f}s")

                # ✅ Final API response
                response_data = {
                    "RecognitionStatus": recognition_status,
                    "Offset": offset,
                    "Duration": duration,
                    "DisplayText": transcribed_text,
                    "file_url": file_url,  # This is now always a WAV file URL
                    "original_format": detected_format,
                    "final_format": "wav",  # Always WAV now
                    "converted": detected_format != 'wav'
                }
                print(f"📤 Sending response: {response_data}")
                print(f"🎤 ===== SPEECH-TO-TEXT API REQUEST COMPLETED =====\n")
                
                return jsonify(response_data), 200

            else:
                print(f"❌ Azure Speech Services error: {azure_response.status_code}")
                print(f"📄 Azure error response: {azure_response.text}")
                print(f"🎤 ===== SPEECH-TO-TEXT API REQUEST FAILED =====\n")
                return jsonify({
                    "error": "Azure Speech Services error",
                    "message": f"Status: {azure_response.status_code}, Response: {azure_response.text}"
                }), 500

        except requests.exceptions.Timeout:
            print(f"⏰ Azure Speech Services request timed out")
            print(f"🎤 ===== SPEECH-TO-TEXT API REQUEST TIMEOUT =====\n")
            return jsonify({
                "error": "Request timeout",
                "message": "Azure Speech Services request timed out"
            }), 504
        except requests.exceptions.RequestException as e:
            print(f"❌ Azure Speech Services request failed: {str(e)}")
            print(f"🎤 ===== SPEECH-TO-TEXT API REQUEST FAILED =====\n")
            return jsonify({
                "error": "Azure Speech Services request failed",
                "message": str(e)
            }), 500

    except Exception as e:
        total_time = time.time() - start_time
        print(f"💥 Unexpected error occurred: {str(e)}")
        print(f"⏱️ Failed after: {total_time:.2f}s")
        print(f"🎤 ===== SPEECH-TO-TEXT API REQUEST ERROR =====\n")
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500