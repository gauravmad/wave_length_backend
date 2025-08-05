from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.services.aws_bucket import handle_image_upload

upload_image_bp = Blueprint("upload_image", __name__)

@upload_image_bp.route("/", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error":"No Image file provided"}), 400
    
    image_file = request.files["image"]
    if image_file.filename == "":
        return jsonify({"error":"Empty filename"}), 400
    
    try:
        image_url = handle_image_upload(image_file)
        return jsonify({"success":True, "image_url": image_url}),200
    
    except Exception as e:
        return jsonify({"success":False, "error":str(e)}), 500