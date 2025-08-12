# app/routes/chat.py
from datetime import datetime
from app.services.db import db
from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.services.claude import get_claude_reply
from app.memory.summary import create_global_summary, compress_summary

chat_bp = Blueprint("chat", __name__)

# Delete Recents Chats
@chat_bp.route('/delete-recent-chats', methods=['DELETE'])
def delete_recent_chats():
    try:
        user_id = request.args.get('userId')
        character_id = request.args.get('characterId')
        count = int(request.args.get('count', 10))  # Default to 10 if not provided

        if not user_id or not character_id:
            return jsonify({"error": "Missing userId or characterId"}), 400

        query = {
            "userId": str(user_id),
            "characterId": str(character_id)
        }

        # Find the most recent N chat IDs
        recent_chats = list(db.chats.find(query).sort("timestamp", -1).limit(count))
        chat_ids_to_delete = [chat["_id"] for chat in recent_chats]

        result = db.chats.delete_many({"_id": {"$in": chat_ids_to_delete}})
        return jsonify({"deletedCount": result.deleted_count}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Delete Chat by ID
@chat_bp.route('/delete-chat/<chat_id>', methods=['DELETE'])
def delete_chat_by_id(chat_id):
    try:
        if not ObjectId.is_valid(chat_id):
            return jsonify({"error": "Invalid chat ID"}), 400

        result = db.chats.delete_one({"_id": ObjectId(chat_id)})

        if result.deleted_count == 0:
            return jsonify({"message": "Chat not found"}), 404

        return jsonify({"message": "Chat deleted successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@chat_bp.route("/generate-summary", methods=["POST"])
def generate_summary_batches():
    try:
        data = request.get_json()
        user_id = data.get("userId")
        character_id = data.get("characterId")

        if not user_id or not character_id:
            return jsonify({"error": "Missing userId or characterId"}), 400

        summary_text = create_global_summary(user_id, character_id)

        return jsonify({
            "message": f"Summary Generated",
            "summaries": summary_text
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500    
    

@chat_bp.route("/compress-summary", methods=["POST"])
def compress_summary_route():
    try:
        data = request.get_json()
        user_id = data.get("userId")
        character_id = data.get("characterId")

        if not user_id or not character_id:
            return jsonify({"error": "Missing userId or characterId"}), 400

        summary_doc = db.summaries.find_one({
            "userId": user_id,
            "characterId": character_id
        })

        if not summary_doc:
            return jsonify({"error": "No summary found to compress"}), 404

        existing_summary = summary_doc.get("summary", "")
        if not existing_summary.strip():
            return jsonify({"error": "Summary is empty"}), 400

        compressed_summary = compress_summary(existing_summary)

        db.summaries.update_one(
            {"_id": summary_doc["_id"]},
            {
                "$set": {
                    "summary": compressed_summary,
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        return jsonify({
            "message": "Summary compressed successfully",
            "summary": compressed_summary
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@chat_bp.route('/get-chats/<user_id>', methods=['GET'])
def get_chats_by_user(user_id):
    try:
        # Query only by userId
        query = {"userId": str(user_id)}

        # Fetch chats sorted by timestamp (latest first)
        chats = list(db.chats.find(query).sort("timestamp", -1))

        # Convert ObjectId to string for JSON
        for chat in chats:
            chat["_id"] = str(chat["_id"])

        return jsonify({
            "count": len(chats),
            "data": chats
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
