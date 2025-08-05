from flask import Blueprint, request, jsonify
import whisper
import os
import tempfile

# Create blueprint
speech_to_text_bp = Blueprint('speech_to_text', __name__)

# Load the Whisper model (you can change to tiny/base/small/medium/large)
model = whisper.load_model("small")  # or "small", "medium", "large"

@speech_to_text_bp.route("/", methods=["POST"])
def transcribe_audio():
    print("📩 Received request to transcribe audio")

    if "file" not in request.files:
        print("❌ No file part in the request")
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    print(f"📦 Received file: {file.filename}")

    if file.filename == "":
        print("❌ No file selected")
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith((".mp3", ".wav", ".opus", ".webm")):
        print("❌ Unsupported file format")
        return jsonify({"error": "Unsupported file format"}), 400

    try:
        # Save the uploaded file to a temp directory
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        os.makedirs(temp_dir, exist_ok=True)

        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        print(f"💾 Saved temp file at: {temp_path}")

        # Transcribe
        print("🧠 Starting transcription...")
        result = model.transcribe(temp_path)
        transcript = result["text"]
        print(f"✅ Transcription done: {transcript}")

        # Clean up
        os.remove(temp_path)
        print("🧹 Temp file deleted")

        return jsonify({"transcript": transcript})

    except Exception as e:
        print(f"🔥 Error during transcription: {str(e)}")
        return jsonify({"error": str(e)}), 500
