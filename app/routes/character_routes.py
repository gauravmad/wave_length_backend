from flask import Blueprint, request, jsonify
from app.services.db import db

character_bp = Blueprint("character_routes", __name__)
characters = db.characters

@character_bp.route("/create", methods=["POST"])
def create_character():
    data = request.json
    required = ["characterName", "characterInfo", "characterImg"]
    if not all(key in data for key in required):
        return jsonify({"error": "Missing fields"}), 400

    # Insert data
    result = characters.insert_one(data)
    return jsonify({
        "message": "Character created",
        "characterId": str(result.inserted_id)  # Mongo's _id
    }), 201

@character_bp.route("/", methods=["GET"])
def get_characters():
    result = list(characters.find({}))
    for character in result:
        character["characterId"] = str(character["_id"])
        del character["_id"]
    return jsonify(result)
