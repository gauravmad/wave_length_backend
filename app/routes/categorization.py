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
            logger.info("--")
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


@user_categorization_bp.route('/generate-all', methods=["POST"])
def generate_all_users_categorization():
    """Generate categorization for all users in the system"""
    try:
        # Get optional parameters
        session_gap = int(request.json.get('session_gap', 30)) if request.json else 30
        force_regenerate = request.json.get('force_regenerate', False) if request.json else False
        
        logger.info(f"Starting bulk categorization for all users with session_gap={session_gap}, force_regenerate={force_regenerate}")
        
        # Fetch all users from the database
        users_cursor = db.users.find({}, {"_id": 1, "userName": 1})
        all_users = list(users_cursor)
        
        if not all_users:
            return jsonify({"error": "No users found in the system"}), 404
        
        logger.info(f"Found {len(all_users)} users to process")
        
        # Initialize Gemini service
        gemini = GeminiService()
        
        # Results tracking
        results = {
            "total_users": len(all_users),
            "processed_users": 0,
            "successful_users": 0,
            "failed_users": 0,
            "skipped_users": 0,
            "user_results": [],
            "started_at": datetime.now().isoformat()
        }
        
        # Process each user
        for idx, user in enumerate(all_users, start=1):
            user_id = str(user["_id"])
            user_name = user.get("userName", "Unknown")
            
            logger.info("")
            logger.info(f"Processing user {idx}/{len(all_users)}: {user_name} (ID: {user_id})")
            
            try:
                # Check if user already has categorization data (unless force regenerate)
                if not force_regenerate:
                    existing_categorization = db.categorizations.find_one({"user_id": user_id})
                    if existing_categorization:
                        logger.info(f"User {user_name} already has categorization data, skipping...")
                        results["skipped_users"] += 1
                        results["user_results"].append({
                            "user_id": user_id,
                            "user_name": user_name,
                            "status": "skipped",
                            "reason": "Already has categorization data"
                        })
                        continue
                
                # Get user sessions
                session_data = calculate_user_sessions_with_chats(user_id, session_gap)
                total_sessions = len(session_data.get("sessions", []))
                
                logger.info(f"User {user_name}: Found {total_sessions} sessions")
                
                if not session_data["sessions"]:
                    logger.warning(f"User {user_name}: No sessions found, skipping...")
                    results["skipped_users"] += 1
                    results["user_results"].append({
                        "user_id": user_id,
                        "user_name": user_name,
                        "status": "skipped",
                        "reason": "No sessions found"
                    })
                    continue
                
                # Process sessions for this user
                user_session_results = []
                
                for session_idx, session in enumerate(session_data["sessions"], start=1):
                    logger.info(f"  Processing session {session_idx}/{total_sessions} for user {user_name}")
                    
                    # Extract messages
                    messages = []
                    for chat in session["chats"]:
                        message = chat.get("message", "").strip()
                        if message and not message.startswith("⚠️"):
                            messages.append(message)
                    
                    if not messages:
                        category_result = {
                            "primary_category": "Other",
                            "sub_category": "N/A"
                        }
                        logger.warning(f"  No valid messages in session {session_idx}, defaulting to Other/N.A")
                    else:
                        try:
                            prompt = create_simple_prompt(messages)
                            response = gemini.generate_response(prompt, temperature=0.3)
                            
                            response = response.strip()
                            if response.startswith("```json"):
                                response = response.replace("```json", "").replace("```", "")
                            
                            category_result = json.loads(response)
                            logger.info(f"  Session {session_idx} categorized: {category_result}")
                        except Exception as e:
                            logger.error(f"  Gemini error for session {session['sessionId']}: {e}")
                            category_result = {
                                "primary_category": "Other", 
                                "sub_category": "N/A",
                                "error": str(e)
                            }
                    
                    # Store session result
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
                    
                    user_session_results.append(session_result)
                
                # Save user categorization to database
                user_doc = {
                    "user_id": user_id,
                    "user_name": user_name,
                    "total_sessions": len(user_session_results),
                    "processed_at": datetime.now().isoformat(),
                    "sessions": user_session_results
                }
                
                db.categorizations.replace_one(
                    {"user_id": user_id},
                    user_doc,
                    upsert=True
                )
                
                logger.info(f"User {user_name}: Saved {len(user_session_results)} sessions to DB")
                
                results["successful_users"] += 1
                results["user_results"].append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "status": "success",
                    "sessions_processed": len(user_session_results)
                })
                
            except Exception as e:
                logger.error(f"Error processing user {user_name} (ID: {user_id}): {e}")
                results["failed_users"] += 1
                results["user_results"].append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "status": "failed",
                    "error": str(e)
                })
            
            results["processed_users"] += 1
        
        # Add completion timestamp
        results["completed_at"] = datetime.now().isoformat()
        
        logger.info(f"Bulk categorization completed: {results['successful_users']} successful, {results['failed_users']} failed, {results['skipped_users']} skipped")
        
        return jsonify({
            "success": True,
            "message": "Bulk categorization completed",
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Error during bulk categorization: {e}")
        return jsonify({"error": str(e)}), 500


# Give me Global Statistics
@user_categorization_bp.route('/global-stats', methods=["GET"])
def get_global_categorization_stats():
    """Get comprehensive global statistics for all users' categorizations with unique user counting"""
    try:
        # Optional query parameters
        limit = int(request.args.get('limit', 100))
        skip = int(request.args.get('skip', 0))
        
        logger.info(f"Fetching global categorization stats with limit={limit}, skip={skip}")
        
        # Fetch all user categorization data with pagination
        cursor = db.categorizations.find().skip(skip).limit(limit)
        all_users_data = list(cursor)
        
        if not all_users_data:
            return jsonify({"error": "No categorization data found"}), 404
        
        # Global counters - now counting unique users, not sessions
        total_users = len(all_users_data)
        total_sessions = 0
        total_chats = 0
        
        # Category counters - now counting unique users by their majority category
        global_category_counts = {}
        global_subcategory_counts = {}
        
        # User-level statistics
        user_stats = []
        emotional_distress_users = []
        
        # Process each user's data
        for user_data in all_users_data:
            user_id = user_data.get("user_id")
            user_name = user_data.get("user_name", "Unknown")
            sessions = user_data.get("sessions", [])
            user_session_count = len(sessions)
            
            if user_session_count == 0:
                continue
            
            total_sessions += user_session_count
            
            # User-level counters
            user_category_counts = {}
            user_subcategory_counts = {}
            user_chat_count = 0
            user_emotional_distress_count = 0
            
            # Process each session for this user
            for session in sessions:
                primary_category = session.get("primary_category", "Other")
                sub_category = session.get("sub_category", "N/A")
                chat_count = session.get("chat_count", 0)
                
                user_chat_count += chat_count
                total_chats += chat_count
                
                # Count categories for this user only
                user_category_counts[primary_category] = user_category_counts.get(primary_category, 0) + 1
                
                # Count subcategories for this user only
                if sub_category and sub_category != "N/A":
                    user_subcategory_counts[sub_category] = user_subcategory_counts.get(sub_category, 0) + 1
                
                # Track emotional distress
                if primary_category == "Emotional Distress":
                    user_emotional_distress_count += 1
            
            # Determine user's majority category (most common category for this user)
            user_majority_category = max(user_category_counts.items(), key=lambda x: x[1])[0] if user_category_counts else "Other"
            user_majority_subcategory = max(user_subcategory_counts.items(), key=lambda x: x[1])[0] if user_subcategory_counts else "N/A"
            
            # Count this user in global category counts (unique user counting)
            global_category_counts[user_majority_category] = global_category_counts.get(user_majority_category, 0) + 1
            
            # Count this user in global subcategory counts if they have a majority subcategory
            if user_majority_subcategory != "N/A":
                global_subcategory_counts[user_majority_subcategory] = global_subcategory_counts.get(user_majority_subcategory, 0) + 1
            
            # Calculate user-level percentages
            user_category_percentages = {}
            for category, count in user_category_counts.items():
                user_category_percentages[category] = round((count / user_session_count) * 100, 2)
            
            user_subcategory_percentages = {}
            for subcategory, count in user_subcategory_counts.items():
                user_subcategory_percentages[subcategory] = round((count / user_session_count) * 100, 2)
            
            # User emotional distress percentage
            user_emotional_distress_percentage = round((user_emotional_distress_count / user_session_count) * 100, 2)
            
            # Store user stats
            user_stat = {
                "user_id": user_id,
                "user_name": user_name,
                "total_sessions": user_session_count,
                "total_chats": user_chat_count,
                "category_percentages": user_category_percentages,
                "subcategory_percentages": user_subcategory_percentages,
                "emotional_distress_percentage": user_emotional_distress_percentage,
                "majority_category": user_majority_category,
                "majority_subcategory": user_majority_subcategory,
                "most_common_category": user_majority_category,  # Keep for backward compatibility
                "most_common_subcategory": user_majority_subcategory  # Keep for backward compatibility
            }
            
            user_stats.append(user_stat)
            
            # Track users with high emotional distress (>30%)
            if user_emotional_distress_percentage > 30:
                emotional_distress_users.append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "emotional_distress_percentage": user_emotional_distress_percentage,
                    "total_sessions": user_session_count
                })
        
        # Calculate global percentages based on unique users
        global_category_percentages = {}
        for category, count in global_category_counts.items():
            global_category_percentages[category] = round((count / total_users) * 100, 2)
        
        global_subcategory_percentages = {}
        total_users_with_subcategories = sum(global_subcategory_counts.values())
        for subcategory, count in global_subcategory_counts.items():
            global_subcategory_percentages[subcategory] = round((count / total_users_with_subcategories) * 100, 2) if total_users_with_subcategories > 0 else 0
        
        # Sort users by emotional distress percentage (highest first)
        user_stats.sort(key=lambda x: x.get("emotional_distress_percentage", 0), reverse=True)
        emotional_distress_users.sort(key=lambda x: x.get("emotional_distress_percentage", 0), reverse=True)
        
        # Calculate averages
        avg_sessions_per_user = round(total_sessions / total_users, 2) if total_users > 0 else 0
        avg_chats_per_user = round(total_chats / total_users, 2) if total_users > 0 else 0
        avg_emotional_distress_percentage = round(sum(user["emotional_distress_percentage"] for user in user_stats) / len(user_stats), 2) if user_stats else 0
        
        # Prepare comprehensive response
        response_data = {
            "success": True,
            "summary": {
                "total_users_analyzed": total_users,
                "total_sessions": total_sessions,
                "total_chats": total_chats,
                "avg_sessions_per_user": avg_sessions_per_user,
                "avg_chats_per_user": avg_chats_per_user,
                "avg_emotional_distress_percentage": avg_emotional_distress_percentage,
                "note": "Category counts represent unique users by their majority category, not total sessions"
            },
            "global_statistics": {
                "primary_categories": {
                    "counts": global_category_counts,
                    "percentages": global_category_percentages,
                    "most_common": max(global_category_counts.items(), key=lambda x: x[1])[0] if global_category_counts else None
                },
                "sub_categories": {
                    "counts": global_subcategory_counts,
                    "percentages": global_subcategory_percentages,
                    "most_common": max(global_subcategory_counts.items(), key=lambda x: x[1])[0] if global_subcategory_counts else None
                }
            },
            "emotional_distress_analysis": {
                "users_with_high_distress": len(emotional_distress_users),
                "high_distress_threshold": 30,
                "top_distressed_users": emotional_distress_users[:10]  # Top 10 most distressed users
            },
            "user_rankings": {
                "by_emotional_distress": user_stats[:20],  # Top 20 users by emotional distress
                "by_session_count": sorted(user_stats, key=lambda x: x["total_sessions"], reverse=True)[:20],  # Top 20 by session count
                "by_chat_count": sorted(user_stats, key=lambda x: x["total_chats"], reverse=True)[:20]  # Top 20 by chat count
            },
            "pagination": {
                "skip": skip,
                "limit": limit,
                "returned_users": len(user_stats)
            },
            "generated_at": datetime.now().isoformat()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error fetching global categorization stats: {e}")
        return jsonify({"error": str(e)}), 500


@user_categorization_bp.route('/health', methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "user_categorization",
        "timestamp": datetime.now().isoformat()
    })