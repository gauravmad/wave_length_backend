from flask import Blueprint, request, jsonify
import random
import requests
from app.config import Config

send_otp_bp = Blueprint("send_otp_bp", __name__)

def generate_otp():
    return str(random.randint(100000, 999999))

@send_otp_bp.route('/', methods=['POST'])
def send_otp():
    data = request.get_json()
    mobile_number = data.get('mobileNumber')

    if not mobile_number:
        return jsonify({"error":"Mobile Number is Required"}), 400
    
    otp = generate_otp()

    payload = {
        "name":"wave-otp-verification",
        "to":{
            "subscriberId":Config.SUBSCRIBER_ID,
            "phone":mobile_number
        },
        "payload":{
            "otp":otp
        }
    }

    headers = {
        "Authorization": f"ApiKey {Config.NOVU_API_KEY}",
        "Content-Type":"application/json"
    }

    try:
        response = requests.post(Config.NOVU_TRIGGER_URL, json=payload, headers=headers)
        if response.status_code == 201:
            return jsonify({"success": True,"otp":otp})
        else:
            return jsonify({"success":False, "message":response.text}),500
        
    except Exception as e:
        return jsonify({"success":False,"message":str(e)}),500    