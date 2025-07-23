from flask import Blueprint, request, jsonify
import random, requests
from itsdangerous import URLSafeTimedSerializer
from app.config import Config

send_otp_bp = Blueprint("send_otp_bp", __name__)
serializer = URLSafeTimedSerializer(Config.SECRET_KEY)

def generate_otp():
    return str(random.randint(100000, 999999))

@send_otp_bp.route('/', methods=['POST'])
def send_otp():
    data = request.get_json()
    mobile_number = data.get('mobileNumber')

    if not mobile_number:
        return jsonify({"error":"Mobile Number is Required"}), 400

    otp = generate_otp()
    print("OTP Trigger", otp)

    # Create token with OTP
    encrypted_otp_token = serializer.dumps(otp, salt="otp-verification")

    payload = {
        "name": "wave-otp-verification",
        "to": {
            "subscriberId": Config.SUBSCRIBER_ID,
            "phone": f"+91{mobile_number}"
        },
        "payload": {
            "otp": int(otp)
        }
    }

    headers = {
        "Authorization": f"ApiKey {Config.NOVU_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(Config.NOVU_TRIGGER_URL, json=payload, headers=headers)
        if response.status_code == 201:
            return jsonify({
                "success": True,
                "encryptedToken": encrypted_otp_token
            })
        else:
            return jsonify({"success": False, "message": response.text}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
