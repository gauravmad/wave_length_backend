from flask import Blueprint, request, jsonify
import jwt
import datetime
from app.config import Config
from ..models.users import create_user, get_all_users, get_user_by_mobile

user_bp = Blueprint("user_bp", __name__)

def generate_token(user_id):
    payload = {
        "user_id":str(user_id),
        "exp":datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    token = jwt.encode(payload,Config.SECRET_KEY, algorithm="HS256")
    return token

@user_bp.route("/", methods=["POST"])
def create():
    data = request.get_json()

    required_fields = ["userName", "mobileNumber", "mobileNumberVerified", "age", "gender"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    user = get_user_by_mobile(data["mobileNumber"])

    # User already exists — treat as login
    if user:
        token = generate_token(user["_id"])
        return jsonify({
            "success": True,
            "message": "Login successful",
            "token": token,
            "data": {
                "userId": str(user["_id"]),
                "userName": user["userName"],
                "mobileNumber": user["mobileNumber"],
                "mobileNumberVerified": user.get("mobileNumberVerified", False),
                "age": user["age"],
                "gender": user["gender"]
            }
        }), 200

    # New user — register
    user_data = {
        "userName": data["userName"],
        "mobileNumber": data["mobileNumber"],
        "mobileNumberVerified": data.get("mobileNumberVerified", False),
        "age": data["age"],
        "gender": data["gender"]
    }

    result = create_user(user_data)
    token = generate_token(result.inserted_id)

    return jsonify({
        "success": True,
        "message": "User registered successfully",
        "token": token,
        "data": {
            "userId": str(result.inserted_id),
            "userName": user_data["userName"],
            "mobileNumber": user_data["mobileNumber"],
            "mobileNumberVerified": user_data["mobileNumberVerified"],
            "age": user_data["age"],
            "gender": user_data["gender"]
        }
    }), 201


@user_bp.route("/", methods=["GET"])
def get_users():
    users = get_all_users()
    for user in users:
        user["_id"] = str(user["_id"])
    return jsonify(users)
