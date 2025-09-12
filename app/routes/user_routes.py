from flask import Blueprint, request, jsonify
import jwt
import datetime
import re
from app.config import Config
from app.services.db import db
from ..models.users import create_user, get_user_by_mobile, get_user_by_id, get_user_by_email

user_bp = Blueprint("user_bp", __name__)

def generate_token(user_id):
    payload = {
        "user_id": str(user_id),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# 🚀 Register Route
@user_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    required_fields = ["userName", "mobileNumber", "email", "mobileNumberVerified", "age", "gender"]
    
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate email format
    if not validate_email(data["email"]):
        return jsonify({"error": "Invalid email format"}), 400

    # Check if user already exists by mobile number
    if get_user_by_mobile(data["mobileNumber"]):
        return jsonify({"success": False, "message": "User with this mobile number already exists"}), 409

    # Check if user already exists by email
    if get_user_by_email(data["email"]):
        return jsonify({"success": False, "message": "User with this email already exists"}), 409

    user_data = {
        "userName": data["userName"],
        "mobileNumber": data["mobileNumber"],
        "email": data["email"].lower(),  # Store email in lowercase
        "mobileNumberVerified": data["mobileNumberVerified"],
        "emailVerified": data.get("emailVerified", False),  # Optional field with default
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
            "email": user_data["email"],
            "mobileNumberVerified": user_data["mobileNumberVerified"],
            "emailVerified": user_data["emailVerified"],
            "age": user_data["age"],
            "gender": user_data["gender"],
            "createdAt": user_data["createdAt"].isoformat(),
            "updatedAt": user_data["updatedAt"].isoformat()
        }
    }), 201

# ✅ Login Route (Mobile Number or Email)
@user_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    login_identifier = data.get("loginIdentifier")  # Can be mobile number or email
    mobile_number = data.get("mobileNumber")  # Backward compatibility
    email = data.get("email")  # Backward compatibility

    # Determine login method
    user = None
    
    if login_identifier:
        # Check if it's an email (contains @) or mobile number
        if "@" in login_identifier:
            if not validate_email(login_identifier):
                return jsonify({"error": "Invalid email format"}), 400
            user = get_user_by_email(login_identifier.lower())
        else:
            user = get_user_by_mobile(login_identifier)
    elif mobile_number:
        # Backward compatibility for mobile number login
        user = get_user_by_mobile(mobile_number)
    elif email:
        # Backward compatibility for email login
        if not validate_email(email):
            return jsonify({"error": "Invalid email format"}), 400
        user = get_user_by_email(email.lower())
    else:
        return jsonify({"error": "Mobile number or email is required"}), 400

    if not user:
        return jsonify({"success": False, "message": "User not found. Please register"}), 404

    token = generate_token(user["_id"])

    return jsonify({
        "success": True,
        "message": "Login successful",
        "token": token,
        "data": {
            "userId": str(user["_id"]),
            "userName": user["userName"],
            "mobileNumber": user["mobileNumber"],
            "email": user.get("email", ""),
            "mobileNumberVerified": user.get("mobileNumberVerified", False),
            "emailVerified": user.get("emailVerified", False),
            "age": user["age"],
            "gender": user["gender"],
            "createdAt": user["createdAt"].isoformat() if "createdAt" in user else None,
            "updatedAt": user["updatedAt"].isoformat() if "updatedAt" in user else None
        }
    }), 200

@user_bp.route("/", methods=["GET"])
def get_users():
    try:
        # Pagination params
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
        search = request.args.get("search", "").strip()

        if page < 1:
            page = 1
        if limit < 1:
            limit = 10

        # Build search query
        search_query = {}
        if search:
            # Search in userName, mobileNumber, and email
            search_query["$or"] = [
                {"userName": {"$regex": search, "$options": "i"}},
                {"mobileNumber": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]

        # Total count with search filter
        total_count = db.users.count_documents(search_query)

        # Pagination math
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
        skip = (page - 1) * limit

        # Fetch paginated users (latest created first) with search filter
        users = list(
            db.users.find(search_query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )

        for user in users:
            user["_id"] = str(user["_id"])
            user["createdAt"] = user["createdAt"].isoformat() if "createdAt" in user and user["createdAt"] else None
            user["updatedAt"] = user["updatedAt"].isoformat() if "updatedAt" in user and user["updatedAt"] else None

        return jsonify({
            "success": True,
            "data": users,
            "total_count": total_count,
            "total_pages": total_pages,
            "page": page,
            "limit": limit,
            "search": search
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
# ✅ Get User by ID Route
@user_bp.route("/getuser/<userid>", methods=["GET"])
def get_user(userid):
    try:
        user = get_user_by_id(userid)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        # Convert ObjectId and datetime fields to string
        user["_id"] = str(user["_id"])
        user["createdAt"] = user["createdAt"].isoformat() if "createdAt" in user and user["createdAt"] else None
        user["updatedAt"] = user["updatedAt"].isoformat() if "updatedAt" in user and user["updatedAt"] else None

        return jsonify({
            "success": True,
            "data": user
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500