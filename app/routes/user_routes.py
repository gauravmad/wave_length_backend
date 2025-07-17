from flask import Blueprint, request, jsonify
from ..models.users import create_user, get_all_users, get_user_by_mobile

user_bp = Blueprint("user_bp", __name__)

@user_bp.route("/", methods=["POST"])
def create():
    data = request.get_json()

    required_fields = ["userName", "mobileNumber", "mobileNumberVerified", "age", "gender"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    user = get_user_by_mobile(data["mobileNumber"])
    if user:
        return jsonify({"message": "User already exists"}), 409

    user_data = {
        "userName": data["userName"],
        "mobileNumber": data["mobileNumber"],
        "mobileNumberVerified": data.get("mobileNumberVerified", False),
        "age": data["age"],
        "gender": data["gender"],
        "sessions": data.get("sessions", [])  # Optional list of session IDs
    }

    result = create_user(user_data)
    return jsonify({
        "success": True,
        "message": "User created Successfully", 
        "data": {
            "userName": user_data["userName"],
            "mobileNumber": user_data["mobileNumber"],
            "mobileNumberVerified": user_data["mobileNumberVerified"],
            "age": user_data["age"],
            "sessions": user_data["sessions"],
        },
        "userId": str(result.inserted_id)
    }), 201


@user_bp.route("/", methods=["GET"])
def get_users():
    users = get_all_users()
    for user in users:
        user["_id"] = str(user["_id"])
    return jsonify(users)
