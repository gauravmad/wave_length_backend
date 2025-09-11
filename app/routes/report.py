from flask import Blueprint, request, jsonify
from app.services.db import db
from datetime import datetime

report_bp = Blueprint("report", __name__)
reports = db.reports

@report_bp.route("/", methods=["POST"])
def submit_report():
    try:
        # Get JSON data from request
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        user_id = data.get("user_id")
        report_type = data.get("report_type")
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
            
        if not report_type:
            return jsonify({"error": "report_type is required"}), 400
        
        # Create report document
        report_data = {
            "user_id": user_id,
            "report_type": report_type,
            "created_at": datetime.utcnow()
        }
        
        # Insert into database
        result = reports.insert_one(report_data)
        
        if result.inserted_id:
            return jsonify({"message": "Report submitted successfully"}), 201
        else:
            return jsonify({"error": "Failed to submit report"}), 500
            
    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    
