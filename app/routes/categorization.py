from flask import Flask, jsonify, Blueprint, request
from app.services.db import db
from app.services.gemini import GeminiService
from app.routes.user_analytics import calculate_user_sessions_with_chats
from datetime import datetime
from bson import ObjectId
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_categorization_bp = Blueprint('user_categorization', __name__)

def create_simple_prompt(messages):
    """Create simple categorization prompt"""
    conversation = "\n".join(messages)
    
    return f"""Categorize this conversation:

Categories:
- Life Update: Sharing news/events
- General Chat: Casual conversation  
- Venting & Complaining: Expressing frustration
- Emotional Distress: Personal emotional struggles
- Romantic: Seeking romantic connection
- Other: Unclear/random content

Sub-categories (only for Emotional Distress):
- Anxiety/Overwhelm
- Sadness/Depression
- Loneliness  
- Self-Doubt/Imposter Syndrome
- Relationship Conflict
- Other

Conversation:
{conversation}

Respond only in JSON:
{{
  "primary_category": "category_name",
  "sub_category": "N/A or subcategory"
}}"""

@user_categorization_bp.route('/', methods=["GET"])
def categorize_user_sessions():
    """Simple session categorization"""
    try:
        user_id = request.args.get('user_id')
        session_gap = int(request.args.get('session_gap', 30))
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        logger.info(f"Processing categorization for user_id={user_id}, session_gap={session_gap}")
        
        # Get user sessions
        session_data = calculate_user_sessions_with_chats(user_id, session_gap)
        total_sessions = len(session_data.get("sessions", []))
        logger.info(f"Total sessions found: {total_sessions}")
        
        if not session_data["sessions"]:
            return jsonify({"error": "No sessions found"}), 404
        
        # Initialize Gemini
        gemini = GeminiService()
        
        results = []
        
        for idx, session in enumerate(session_data["sessions"], start=1):
            logger.info(f"Processing Session {idx} (sessionId={session['sessionId']})")
            
            # Extract just the messages
            messages = []
            for chat in session["chats"]:
                message = chat.get("message", "").strip()
                if message and not message.startswith("⚠️"):
                    messages.append(message)
            
            logger.info(f"Chats fetched: {len(messages)} for Session {idx}")
            
            if not messages:
                category_result = {
                    "primary_category": "Other",
                    "sub_category": "N/A"
                }
                logger.warning(f"No valid messages in Session {idx}, defaulting to Other/N.A")
            else:
                try:
                    prompt = create_simple_prompt(messages)
                    response = gemini.generate_response(prompt, temperature=0.3)
                    
                    response = response.strip()
                    if response.startswith("```json"):
                        response = response.replace("```json", "").replace("```", "")
                    
                    category_result = json.loads(response)
                    logger.info(f"Gemini categorized Session {idx}: {category_result}")
                except Exception as e:
                    logger.error(f"Gemini error for session {session['sessionId']}: {e}")
                    category_result = {
                        "primary_category": "Other", 
                        "sub_category": "N/A",
                        "error": str(e)
                    }
            
            # Store result
            session_result = {
                "session_id": session["sessionId"],
                "user_id": user_id,
                "primary_category": category_result["primary_category"],
                "sub_category": category_result.get("sub_category", "N/A"),
                "session_start": session["startTime"],
                "session_end": session["endTime"], 
                "chat_count": session["chatCount"],
                "duration_minutes": session["durationMinutes"],
                "processed_at": datetime.now().isoformat()
            }
            
            results.append(session_result)
            logger.info(f"Session {idx} result stored: {session_result['session_id']}")
        
        # Save to database - one document per user
        user_doc = {
            "user_id": user_id,
            "total_sessions": len(results),
            "processed_at": datetime.now().isoformat(),
            "sessions": results
        }
        
        db.categorizations.replace_one(
            {"user_id": user_id},
            user_doc,
            upsert=True
        )
        
        logger.info(f"Saved {len(results)} sessions to DB for user_id={user_id}")
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "sessions_processed": len(results),
            "data": results
        })
        
    except Exception as e:
        logger.error(f"Error during categorization for user_id={user_id if 'user_id' in locals() else 'N/A'}: {e}")
        return jsonify({"error": str(e)}), 500


@user_categorization_bp.route('/stats/<user_id>', methods=["GET"])
def get_user_categorization_stats(user_id):
    """Get categorization statistics for a user with scores out of 100"""
    try:
        # Fetch user categorization data
        user_data = db.categorizations.find_one({"user_id": user_id})
        
        if not user_data:
            return jsonify({"error": "No categorization data found for this user"}), 404
        
        sessions = user_data.get("sessions", [])
        total_sessions = len(sessions)
        
        if total_sessions == 0:
            return jsonify({"error": "No sessions found for this user"}), 404
        
        # Initialize counters
        category_counts = {}
        subcategory_counts = {}
        
        # Count categories and subcategories
        for session in sessions:
            primary_category = session.get("primary_category", "Other")
            sub_category = session.get("sub_category", "N/A")
            
            # Count primary categories
            category_counts[primary_category] = category_counts.get(primary_category, 0) + 1
            
            # Count subcategories (only for non-N/A values)
            if sub_category and sub_category != "N/A":
                subcategory_counts[sub_category] = subcategory_counts.get(sub_category, 0) + 1
        
        # Calculate percentages (scores out of 100)
        category_stats = {}
        for category, count in category_counts.items():
            category_stats[category] = {
                "count": count,
                "score": round((count / total_sessions) * 100, 2)
            }
        
        subcategory_stats = {}
        for subcategory, count in subcategory_counts.items():
            subcategory_stats[subcategory] = {
                "count": count,
                "score": round((count / total_sessions) * 100, 2)
            }
        
        # Get the most common category and subcategory
        most_common_category = max(category_counts.items(), key=lambda x: x[1]) if category_counts else None
        most_common_subcategory = max(subcategory_counts.items(), key=lambda x: x[1]) if subcategory_counts else None
        
        # Calculate emotional distress sessions specifically
        emotional_distress_count = category_counts.get("Emotional Distress", 0)
        emotional_distress_score = round((emotional_distress_count / total_sessions) * 100, 2) if total_sessions > 0 else 0
        
        # Prepare response
        response_data = {
            "success": True,
            "user_id": user_id,
            "total_sessions": total_sessions,
            "processed_at": user_data.get("processed_at"),
            "statistics": {
                "primary_categories": category_stats,
                "sub_categories": subcategory_stats,
                "summary": {
                    "most_common_category": {
                        "name": most_common_category[0] if most_common_category else None,
                        "count": most_common_category[1] if most_common_category else 0,
                        "score": round((most_common_category[1] / total_sessions) * 100, 2) if most_common_category else 0
                    },
                    "most_common_subcategory": {
                        "name": most_common_subcategory[0] if most_common_subcategory else None,
                        "count": most_common_subcategory[1] if most_common_subcategory else 0,
                        "score": round((most_common_subcategory[1] / total_sessions) * 100, 2) if most_common_subcategory else 0
                    },
                    "emotional_distress": {
                        "count": emotional_distress_count,
                        "score": emotional_distress_score
                    }
                }
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error fetching stats for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500


@user_categorization_bp.route('/stats', methods=["GET"])
def get_all_users_categorization_stats():
    """Get categorization statistics for all users or filter by query parameters"""
    try:
        # Optional query parameters
        limit = int(request.args.get('limit', 10))
        skip = int(request.args.get('skip', 0))
        
        # Fetch all user categorization data with pagination
        cursor = db.categorizations.find().skip(skip).limit(limit)
        all_users_data = list(cursor)
        
        if not all_users_data:
            return jsonify({"error": "No categorization data found"}), 404
        
        users_stats = []
        
        for user_data in all_users_data:
            user_id = user_data.get("user_id")
            sessions = user_data.get("sessions", [])
            total_sessions = len(sessions)
            
            if total_sessions == 0:
                continue
            
            # Count categories for this user
            category_counts = {}
            subcategory_counts = {}
            
            for session in sessions:
                primary_category = session.get("primary_category", "Other")
                sub_category = session.get("sub_category", "N/A")
                
                category_counts[primary_category] = category_counts.get(primary_category, 0) + 1
                
                if sub_category and sub_category != "N/A":
                    subcategory_counts[sub_category] = subcategory_counts.get(sub_category, 0) + 1
            
            # Calculate scores for this user
            category_stats = {}
            for category, count in category_counts.items():
                category_stats[category] = round((count / total_sessions) * 100, 2)
            
            subcategory_stats = {}
            for subcategory, count in subcategory_counts.items():
                subcategory_stats[subcategory] = round((count / total_sessions) * 100, 2)
            
            # Most common category for this user
            most_common_category = max(category_counts.items(), key=lambda x: x[1]) if category_counts else None
            
            user_stat = {
                "user_id": user_id,
                "total_sessions": total_sessions,
                "processed_at": user_data.get("processed_at"),
                "primary_category_scores": category_stats,
                "sub_category_scores": subcategory_stats,
                "most_common_category": most_common_category[0] if most_common_category else None,
                "emotional_distress_score": category_stats.get("Emotional Distress", 0)
            }
            
            users_stats.append(user_stat)
        
        # Sort by emotional distress score (highest first)
        users_stats.sort(key=lambda x: x.get("emotional_distress_score", 0), reverse=True)
        
        return jsonify({
            "success": True,
            "total_users": len(users_stats),
            "users": users_stats,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "returned": len(users_stats)
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching all users stats: {e}")
        return jsonify({"error": str(e)}), 500


@user_categorization_bp.route('/health', methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "user_categorization",
        "timestamp": datetime.now().isoformat()
    })