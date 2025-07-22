from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import Config

verify_otp_bp = Blueprint("verify_otp_bp", __name__)
serializer = URLSafeTimedSerializer(Config.SECRET_KEY)

@verify_otp_bp.route("/", methods=["POST"])
def verify_otp():
    data = request.get_json()
    encrypted_token = data.get("encryptedToken")
    entered_otp = data.get("otp")

    if not encrypted_token or not entered_otp:
        return jsonify({"error": "OTP and Token are required"}), 400

    try:
        # Decode the OTP with max age of 5 minutes (300 seconds)
        original_otp = serializer.loads(
            encrypted_token,
            salt="otp-verification",
            max_age=300
        )
    except SignatureExpired:
        return jsonify({"error": "OTP token expired"}), 400
    except BadSignature:
        return jsonify({"error": "Invalid token"}), 400

    if entered_otp != original_otp:
        return jsonify({"error": "Invalid OTP"}), 401

    return jsonify({"success": True, "message": "OTP verified successfully"}), 200
