# app/routes/chat.py

from flask import Blueprint, request, jsonify
from app.services.claude import get_claude_reply

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/", methods=["POST"])
def test_claude():
    try:
        data = request.get_json()
        prompt = data.get("prompt")
        user_id = data.get("userId")
        character_name = data.get("characterName")
        character_id = data.get("characterId")

        if not all([prompt, user_id, character_name, character_id]):
            return jsonify({"error": "Missing required fields"}), 400

        reply = get_claude_reply(prompt, user_id, character_name, character_id)
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
