from flask import Flask, jsonify, Blueprint, request
from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import defaultdict
from bson import ObjectId
from app.config import Config
from app.services.db import db

user_analytics_bp = Blueprint('user_analytics', __name__)

def parse_timestamp(timestamp_str):
    """Parse timestamp string to datetime object"""
    try:
        # Handle the format "2025-07-24T16:04:09.193708"
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except:
        try:
            # Try alternative formats
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
        except:
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")

def get_session_categorization(user_id, session_id):
    """Get categorization data for a specific session from categorization collection"""
    try:
        # Find user's categorization data
        user_categorization = db.categorizations.find_one({"user_id": user_id})
        
        if not user_categorization or not user_categorization.get("sessions"):
            return {
                "primary_category": "Not Categorized",
                "sub_category": "N/A"
            }
        
        # Find the specific session in categorization data
        for session in user_categorization["sessions"]:
            if session.get("session_id") == session_id:
                return {
                    "primary_category": session.get("primary_category", "Not Categorized"),
                    "sub_category": session.get("sub_category", "N/A")
                }
        
        # If session not found in categorization data
        return {
            "primary_category": "Not Categorized", 
            "sub_category": "N/A"
        }
        
    except Exception as e:
        # Return default values if any error occurs
        return {
            "primary_category": "Not Categorized",
            "sub_category": "N/A"
        }

def get_day_categorization(user_id, date_str, day_sessions):
    """Get categorization data for a specific day based on sessions within that day"""
    try:
        # Find user's categorization data
        user_categorization = db.categorizations.find_one({"user_id": user_id})
        
        if not user_categorization or not user_categorization.get("sessions"):
            return {
                "primary_category": "Not Categorized",
                "sub_category": "N/A"
            }
        
        # Collect all categories for sessions that occur on this day
        day_categories = []
        for session_data in day_sessions:
            # For each session in the day, find its categorization
            for session in user_categorization["sessions"]:
                if session.get("session_id") == session_data.get("session_id"):
                    day_categories.append({
                        "primary_category": session.get("primary_category", "Not Categorized"),
                        "sub_category": session.get("sub_category", "N/A")
                    })
        
        if not day_categories:
            return {
                "primary_category": "Not Categorized",
                "sub_category": "N/A"
            }
        
        # If multiple sessions in a day, use the most frequent primary category
        primary_counts = {}
        for cat in day_categories:
            primary = cat["primary_category"]
            if primary in primary_counts:
                primary_counts[primary] += 1
            else:
                primary_counts[primary] = 1
        
        # Get the most frequent primary category
        most_frequent_primary = max(primary_counts, key=primary_counts.get)
        
        # Get corresponding sub_category for the most frequent primary
        corresponding_sub = "N/A"
        for cat in day_categories:
            if cat["primary_category"] == most_frequent_primary:
                corresponding_sub = cat["sub_category"]
                break
        
        return {
            "primary_category": most_frequent_primary,
            "sub_category": corresponding_sub,
            "session_categories": day_categories  # Include all session categories for reference
        }
        
    except Exception as e:
        return {
            "primary_category": "Not Categorized",
            "sub_category": "N/A"
        }

def calculate_user_sessions(user_id, session_gap_minutes=30):
    """Calculate sessions for a specific user based on continuous chat activity"""
    
    # Get all chats for the user, sorted by timestamp
    chats = list(db.chats.find(
        {"userId": user_id}
    ).sort("timestamp", 1))
    
    if not chats:
        return {
            "userId": user_id,
            "totalChats": 0,
            "totalSessions": 0,
            "sessions": [],
            "totalDurationMinutes": 0
        }
    
    sessions = []
    session_gap_seconds = session_gap_minutes * 60
    
    current_session_chats = []
    
    for i, chat in enumerate(chats):
        chat_time = parse_timestamp(chat["timestamp"])
        
        if i == 0:
            # First chat starts the first session
            current_session_chats = [chat]
        else:
            # Check gap between current chat and previous chat
            prev_chat_time = parse_timestamp(chats[i-1]["timestamp"])
            time_gap = (chat_time - prev_chat_time).total_seconds()
            
            if time_gap <= session_gap_seconds:
                # Continue current session
                current_session_chats.append(chat)
            else:
                # Gap is too large, finalize current session and start new one
                if current_session_chats:
                    sessions.append(current_session_chats)
                
                # Start new session with current chat
                current_session_chats = [chat]
    
    # Don't forget the last session
    if current_session_chats:
        sessions.append(current_session_chats)
    
    # Format sessions for response
    formatted_sessions = []
    total_duration = 0
    
    for session_idx, session_chats in enumerate(sessions):
        if not session_chats:
            continue
            
        start_time = parse_timestamp(session_chats[0]["timestamp"])
        end_time = parse_timestamp(session_chats[-1]["timestamp"])
        
        # Calculate session duration (from first chat to last chat)
        session_duration = (end_time - start_time).total_seconds() / 60
        
        formatted_chats = []
        for chat in session_chats:
            formatted_chats.append({
                "chatId": str(chat["_id"]),
                "message": chat.get("message", ""),
                "timestamp": chat["timestamp"],
                "sender": chat.get("sender", "")
            })
        
        # Get categorization data for this session
        session_categorization = get_session_categorization(user_id, session_idx + 1)
        
        formatted_session = {
            "sessionId": session_idx + 1,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "chatCount": len(session_chats),
            "durationMinutes": round(session_duration, 2),
            "categorization": session_categorization
        }
        
        formatted_sessions.append(formatted_session)
        total_duration += session_duration
    
    return {
        "userId": user_id,
        "totalChats": len(chats),
        "totalSessions": len(sessions),
        "sessions": formatted_sessions,
        "totalDurationMinutes": round(total_duration, 2)
    }

def calculate_user_sessions_with_chats(user_id, session_gap_minutes=30):
    """Calculate sessions for a specific user with detailed chat information"""
    
    # Get all chats for the user, sorted by timestamp
    chats = list(db.chats.find(
        {"userId": user_id}
    ).sort("timestamp", 1))
    
    if not chats:
        return {
            "userId": user_id,
            "totalChats": 0,
            "totalSessions": 0,
            "sessions": [],
            "totalDurationMinutes": 0
        }
    
    sessions = []
    session_gap_seconds = session_gap_minutes * 60
    
    current_session_chats = []
    
    for i, chat in enumerate(chats):
        chat_time = parse_timestamp(chat["timestamp"])
        
        if i == 0:
            # First chat starts the first session
            current_session_chats = [chat]
        else:
            # Check gap between current chat and previous chat
            prev_chat_time = parse_timestamp(chats[i-1]["timestamp"])
            time_gap = (chat_time - prev_chat_time).total_seconds()
            
            if time_gap <= session_gap_seconds:
                # Continue current session
                current_session_chats.append(chat)
            else:
                # Gap is too large, finalize current session and start new one
                if current_session_chats:
                    sessions.append(current_session_chats)
                
                # Start new session with current chat
                current_session_chats = [chat]
    
    # Don't forget the last session
    if current_session_chats:
        sessions.append(current_session_chats)
    
    # Format sessions for response with detailed chat information
    formatted_sessions = []
    total_duration = 0
    
    for session_idx, session_chats in enumerate(sessions):
        if not session_chats:
            continue
            
        start_time = parse_timestamp(session_chats[0]["timestamp"])
        end_time = parse_timestamp(session_chats[-1]["timestamp"])
        
        # Calculate session duration (from first chat to last chat)
        session_duration = (end_time - start_time).total_seconds() / 60
        
        # Format chat details for this session
        formatted_chats = []
        user_message_count = 0
        bot_message_count = 0
        
        for chat in session_chats:
            sender = chat.get("sender", "User")
            if sender.lower() == "user":
                user_message_count += 1
            else:
                bot_message_count += 1
                
            formatted_chats.append({
                "chatId": str(chat["_id"]),
                "message": chat.get("message", ""),
                "sender": sender
            })
        
        # Calculate session statistics
        total_characters = sum(len(chat.get("message", "")) for chat in session_chats)
        avg_message_length = total_characters / len(session_chats) if session_chats else 0
        
        # Get categorization data for this session
        session_categorization = get_session_categorization(user_id, session_idx + 1)
        
        formatted_session = {
            "sessionId": session_idx + 1,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "chatCount": len(session_chats),
            "userMessages": user_message_count,
            "botMessages": bot_message_count,
            "durationMinutes": round(session_duration, 2),
            "chats": formatted_chats,  # Include all chat details
            "categorization": session_categorization
        }
        
        formatted_sessions.append(formatted_session)
        total_duration += session_duration
    
    return {
        "userId": user_id,
        "totalChats": len(chats),
        "totalSessions": len(sessions),
        "sessions": formatted_sessions,
        "totalDurationMinutes": round(total_duration, 2),
        "avgSessionDuration": round(total_duration / len(sessions), 2) if sessions else 0,
        "avgChatsPerSession": round(len(chats) / len(sessions), 2) if sessions else 0
    }


@user_analytics_bp.route('/sessions', methods=['GET'])
def get_all_users_sessions():

    """
    API 1: Get all users with their session analysis
    Query params:
    - session_gap: minutes between chats to consider new session (default: 30)
    - user_id: specific user ID (optional)
    - include_chats: include detailed chat information in sessions (default: false)
    - limit: limit number of users returned (optional)
    - skip: skip number of users for pagination (optional)
    - search: search by name, email, or mobile number (optional)
    """
    
    try:
        session_gap = int(request.args.get('session_gap', 60))
        specific_user_id = request.args.get('user_id')
        include_chats = request.args.get('include_chats', 'false').lower() == 'true'
        limit = request.args.get('limit')
        skip = request.args.get('skip', 0)
        search_query = request.args.get('search', '').strip()
        
        if limit:
            limit = int(limit)
        if skip:
            skip = int(skip)
        
        if specific_user_id:
            # Get specific user data
            user = db.users.find_one({"_id": ObjectId(specific_user_id)})
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Use detailed function if chats are requested, otherwise use original
            if include_chats:
                user_session_data = calculate_user_sessions_with_chats(specific_user_id, session_gap)
            else:
                user_session_data = calculate_user_sessions(specific_user_id, session_gap)
            
            # Add user info
            user_session_data.update({
                "userName": user.get("userName"),
                "mobileNumber": user.get("mobileNumber"),
                "age": user.get("age"),
                "gender": user.get("gender"),
                "createdAt": user.get("createdAt"),
                "lastActiveAt": user.get("lastActiveAt")
            })
            
            return jsonify({
                "success": True,
                "includeChats": include_chats,
                "data": user_session_data
            })
        
        # Build search query if search parameter is provided
        search_filter = {}
        if search_query:
            # Create regex pattern for case-insensitive search
            regex_pattern = {"$regex": search_query, "$options": "i"}
            search_filter = {
                "$or": [
                    {"userName": regex_pattern},
                    {"mobileNumber": regex_pattern},
                    {"email": regex_pattern}
                ]
            }
        
        # Get all users with pagination and search filter
        users_query = db.users.find(search_filter)
        if skip:
            users_query = users_query.skip(skip)
        if limit:
            users_query = users_query.limit(limit)
            
        users = list(users_query)
        all_users_sessions = []
        
        for user in users:
            user_id = str(user["_id"])
            
            # Use appropriate function based on include_chats parameter
            if include_chats:
                user_session_data = calculate_user_sessions_with_chats(user_id, session_gap)
            else:
                user_session_data = calculate_user_sessions(user_id, session_gap)
            
            # Add user info
            user_session_data.update({
                "userName": user.get("userName"),
                "mobileNumber": user.get("mobileNumber"),
                "age": user.get("age"),
                "gender": user.get("gender"),
                "createdAt": user.get("createdAt"),
                "lastActiveAt": user.get("lastActiveAt")
            })
            
            all_users_sessions.append(user_session_data)
        
        # Sort by total chats descending
        all_users_sessions.sort(key=lambda x: x["totalChats"], reverse=True)
        
        # Get total count for pagination info (with search filter applied)
        total_users = db.users.count_documents({})
        total_filtered_users = db.users.count_documents(search_filter)
        
        return jsonify({
            "success": True,
            "totalUsers": len(all_users_sessions),
            "totalUsersInDB": total_users,
            "totalFilteredUsers": total_filtered_users,
            "sessionGapMinutes": session_gap,
            "includeChats": include_chats,
            "searchQuery": search_query if search_query else None,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "hasMore": (skip + len(all_users_sessions)) < total_filtered_users if limit else False
            },
            "data": all_users_sessions
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Additional endpoint for getting detailed session information for a specific session
@user_analytics_bp.route('/session-details', methods=['GET'])
def get_session_details():
    """
    Get detailed information for a specific session
    Query params:
    - user_id: required
    - session_id: session number (1-based index)
    - session_gap: minutes between chats to consider new session (default: 30)
    """
    
    try:
        user_id = request.args.get('user_id')
        session_id = request.args.get('session_id')
        session_gap = int(request.args.get('session_gap', 30))
        
        if not user_id or not session_id:
            return jsonify({"error": "user_id and session_id are required"}), 400
        
        session_id = int(session_id)
        
        # Get user sessions with chats
        user_session_data = calculate_user_sessions_with_chats(user_id, session_gap)
        
        # Find the specific session
        target_session = None
        for session in user_session_data["sessions"]:
            if session["sessionId"] == session_id:
                target_session = session
                break
        
        if not target_session:
            return jsonify({"error": f"Session {session_id} not found for user {user_id}"}), 404
        
        # Get user info
        user = db.users.find_one({"_id": ObjectId(user_id)})
        
        return jsonify({
            "success": True,
            "userData": {
                "userId": user_id,
                "userName": user.get("userName") if user else None,
                "mobileNumber": user.get("mobileNumber") if user else None
            },
            "sessionData": target_session
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_user_activity_days(user_id, days_back=30):
    """Get days when user was active (had chats)"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Get all chats for user in the date range
    chats = db.chats.find({
        "userId": user_id,
        "timestamp": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    })
    
    active_days = set()
    for chat in chats:
        chat_date = parse_timestamp(chat["timestamp"]).date()
        active_days.add(chat_date)
    
    return sorted(list(active_days))


def categorize_user_activity(user_id):
    """Categorize user as daily/weekly/monthly active"""
    
    # Get activity for last 30 days
    active_days = get_user_activity_days(user_id, 30)
    
    if not active_days:
        return "inactive"
    
    # Check daily active (active 4+ days in last 7 days)
    last_7_days = [datetime.now().date() - timedelta(days=i) for i in range(7)]
    recent_active_days = [day for day in active_days if day in last_7_days]
    
    if len(recent_active_days) >= 4:
        return "daily_active"
    
    # Check weekly active (active 2-3 days in last 7 days)
    elif len(recent_active_days) >= 2:
        return "weekly_active"
    
    # Check monthly active (active at least once in last 30 days)
    elif len(active_days) >= 1:
        return "monthly_active"
    
    else:
        return "inactive"

@user_analytics_bp.route('/activity-analysis', methods=['GET'])
def get_users_activity_analysis():
    """
    API 2: Get user activity analysis (Daily/Weekly/Monthly Active Users)
    Query params:
    - category: filter by category (daily_active, weekly_active, monthly_active, inactive)
    - include_sessions: include session data (default: false)
    """
    
    try:
        category_filter = request.args.get('category')
        include_sessions = request.args.get('include_sessions', 'false').lower() == 'true'
        
        # Get all users
        users = list(db.users.find())
        
        categorized_users = {
            "daily_active": [],
            "weekly_active": [], 
            "monthly_active": [],
            "inactive": []
        }
        
        for user in users:
            user_id = str(user["_id"])
            
            # Get user activity category
            activity_category = categorize_user_activity(user_id)
            
            # Get recent activity stats
            active_days_7 = len(get_user_activity_days(user_id, 7))
            active_days_30 = len(get_user_activity_days(user_id, 30))
            
            # Get total chats
            total_chats = db.chats.count_documents({"userId": user_id})
            
            user_data = {
                "userId": user_id,
                "userName": user.get("userName"),
                "mobileNumber": user.get("mobileNumber"),
                "age": user.get("age"),
                "gender": user.get("gender"),
                "totalChats": total_chats,
                "activeDaysLast7": active_days_7,
                "activeDaysLast30": active_days_30,
                "lastActiveDay": max(get_user_activity_days(user_id, 30)) if get_user_activity_days(user_id, 30) else None
            }
            
            # Include session data if requested
            if include_sessions:
                session_data = calculate_user_sessions(user_id)
                user_data.update({
                    "totalSessions": session_data["totalSessions"],
                    "totalDurationMinutes": session_data["totalDurationMinutes"],
                    "sessions": session_data["sessions"]
                })
            
            categorized_users[activity_category].append(user_data)
        
        # Sort each category by total chats
        for category in categorized_users:
            categorized_users[category].sort(key=lambda x: x["totalChats"], reverse=True)
        
        # Apply category filter if specified
        if category_filter and category_filter in categorized_users:
            return jsonify({
                "success": True,
                "category": category_filter,
                "count": len(categorized_users[category_filter]),
                "users": categorized_users[category_filter]
            })
        
        # Return summary with all categories
        summary = {
            "daily_active_count": len(categorized_users["daily_active"]),
            "weekly_active_count": len(categorized_users["weekly_active"]),
            "monthly_active_count": len(categorized_users["monthly_active"]),
            "inactive_count": len(categorized_users["inactive"]),
            "total_users": len(users)
        }
        
        return jsonify({
            "success": True,
            "summary": summary,
            "data": categorized_users
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@user_analytics_bp.route('/daily-stats', methods=['GET'])
def get_daily_user_stats():
    """Get daily user statistics for specific dates"""
    
    try:
        # Get date parameter (default to today)
        date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get users who were active on this date
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date, datetime.max.time())
        
        # Find all chats on this date
        daily_chats = list(db.chats.find({
            "timestamp": {
                "$gte": start_time.isoformat(),
                "$lte": end_time.isoformat()
            }
        }))
        
        # Get unique users who chatted on this date
        active_user_ids = list(set(chat["userId"] for chat in daily_chats))
        
        # Get user details
        active_users = []
        for user_id in active_user_ids:
            user = db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                user_chats_today = [chat for chat in daily_chats if chat["userId"] == user_id]
                
                active_users.append({
                    "userId": user_id,
                    "userName": user.get("userName"),
                    "mobileNumber": user.get("mobileNumber"),
                    "chatsToday": len(user_chats_today),
                    "firstChatTime": min(chat["timestamp"] for chat in user_chats_today),
                    "lastChatTime": max(chat["timestamp"] for chat in user_chats_today)
                })
        
        return jsonify({
            "success": True,
            "date": date_str,
            "totalActiveUsers": len(active_users),
            "totalChatsToday": len(daily_chats),
            "activeUsers": sorted(active_users, key=lambda x: x["chatsToday"], reverse=True)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def calculate_user_day_wise_analytics(user_id, start_date=None, end_date=None):
    """Calculate day-wise analytics for a specific user"""
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=30)  # Default to last 30 days
    
    # Ensure start_date is before end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # Get all chats for the user in the date range
    chats = list(db.chats.find({
        "userId": user_id,
        "timestamp": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }).sort("timestamp", 1))
    
    # Group chats by day
    daily_data = defaultdict(lambda: {
        "date": None,
        "chatCount": 0,
        "chats": [],
        "durationMinutes": 0,
        "firstChatTime": None,
        "lastChatTime": None,
        "userMessages": 0,
        "botMessages": 0
    })
    
    for chat in chats:
        chat_time = parse_timestamp(chat["timestamp"])
        chat_date = chat_time.date()
        date_str = chat_date.strftime('%Y-%m-%d')
        
        # Initialize day data
        if daily_data[date_str]["date"] is None:
            daily_data[date_str]["date"] = date_str
            daily_data[date_str]["firstChatTime"] = chat["timestamp"]
        
        # Update day data
        daily_data[date_str]["chatCount"] += 1
        daily_data[date_str]["lastChatTime"] = chat["timestamp"]
        daily_data[date_str]["chats"].append({
            "chatId": str(chat["_id"]),
            "message": chat.get("message", ""),
            "timestamp": chat["timestamp"],
            "sender": chat.get("sender", "User")
        })
        
        # Count messages by sender
        sender = chat.get("sender", "User")
        if sender.lower() == "user":
            daily_data[date_str]["userMessages"] += 1
        else:
            daily_data[date_str]["botMessages"] += 1
    
    # Calculate proper session-based duration for each day
    for date_str in daily_data:
        day_data = daily_data[date_str]
        day_chats = day_data["chats"]
        
        if len(day_chats) <= 1:
            day_data["durationMinutes"] = 0
            continue
        
        # Group chats into sessions based on time gaps (similar to session analytics)
        session_gap_seconds = 30 * 60  # 30 minutes gap
        sessions = []
        current_session = [day_chats[0]]
        
        for i in range(1, len(day_chats)):
            current_chat_time = parse_timestamp(day_chats[i]["timestamp"])
            prev_chat_time = parse_timestamp(day_chats[i-1]["timestamp"])
            time_gap = (current_chat_time - prev_chat_time).total_seconds()
            
            if time_gap <= session_gap_seconds:
                current_session.append(day_chats[i])
            else:
                sessions.append(current_session)
                current_session = [day_chats[i]]
        
        # Add the last session
        if current_session:
            sessions.append(current_session)
        
        # Calculate total duration from all sessions
        total_duration = 0
        for session in sessions:
            if len(session) > 1:
                session_start = parse_timestamp(session[0]["timestamp"])
                session_end = parse_timestamp(session[-1]["timestamp"])
                session_duration = (session_end - session_start).total_seconds() / 60
                total_duration += session_duration
        
        day_data["durationMinutes"] = round(total_duration, 2)
        
        # Store session information for categorization
        day_data["sessions"] = sessions
    
    # Get user's full session data for categorization mapping
    user_session_data = calculate_user_sessions(user_id, 30)
    
    # Convert to list and sort by date
    daily_analytics = []
    for date_str in sorted(daily_data.keys()):
        day_data = daily_data[date_str]
        
        # Map day sessions to user sessions for categorization
        day_sessions_for_categorization = []
        for session_idx, session in enumerate(user_session_data.get("sessions", [])):
            session_date = parse_timestamp(session["startTime"]).date().strftime('%Y-%m-%d')
            if session_date == date_str:
                day_sessions_for_categorization.append({
                    "session_id": session["sessionId"],
                    "categorization": session.get("categorization", {})
                })
        
        # Get categorization for this day
        day_categorization = get_day_categorization(user_id, date_str, day_sessions_for_categorization)
        
        # Remove detailed chats from response (can be included optionally)
        day_summary = {
            "date": day_data["date"],
            "chatCount": day_data["chatCount"],
            "durationMinutes": day_data["durationMinutes"],
            "firstChatTime": day_data["firstChatTime"],
            "lastChatTime": day_data["lastChatTime"],
            "userMessages": day_data["userMessages"],
            "botMessages": day_data["botMessages"],
            "categorization": {
                "primary_category": day_categorization["primary_category"],
                "sub_category": day_categorization["sub_category"]
            }
        }
        daily_analytics.append(day_summary)
    
    # Calculate summary statistics
    total_chats = sum(day["chatCount"] for day in daily_analytics)
    total_duration = sum(day["durationMinutes"] for day in daily_analytics)
    active_days = len(daily_analytics)
    avg_chats_per_day = total_chats / active_days if active_days > 0 else 0
    avg_duration_per_day = total_duration / active_days if active_days > 0 else 0
    
    return {
        "userId": user_id,
        "dateRange": {
            "startDate": start_date.strftime('%Y-%m-%d'),
            "endDate": end_date.strftime('%Y-%m-%d'),
            "totalDays": (end_date - start_date).days + 1
        },
        "summary": {
            "totalChats": total_chats,
            "totalDurationMinutes": round(total_duration, 2),
            "activeDays": active_days,
            "avgChatsPerDay": round(avg_chats_per_day, 2),
            "avgDurationPerDay": round(avg_duration_per_day, 2)
        },
        "dailyAnalytics": daily_analytics
    }

def calculate_user_day_wise_analytics_with_chats(user_id, start_date=None, end_date=None):
    """Calculate day-wise analytics for a specific user with detailed chat information"""
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=30)  # Default to last 30 days
    
    # Ensure start_date is before end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # Get all chats for the user in the date range
    chats = list(db.chats.find({
        "userId": user_id,
        "timestamp": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }).sort("timestamp", 1))
    
    # Group chats by day
    daily_data = defaultdict(lambda: {
        "date": None,
        "chatCount": 0,
        "chats": [],
        "durationMinutes": 0,
        "firstChatTime": None,
        "lastChatTime": None,
        "userMessages": 0,
        "botMessages": 0
    })
    
    for chat in chats:
        chat_time = parse_timestamp(chat["timestamp"])
        chat_date = chat_time.date()
        date_str = chat_date.strftime('%Y-%m-%d')
        
        # Initialize day data
        if daily_data[date_str]["date"] is None:
            daily_data[date_str]["date"] = date_str
            daily_data[date_str]["firstChatTime"] = chat["timestamp"]
        
        # Update day data
        daily_data[date_str]["chatCount"] += 1
        daily_data[date_str]["lastChatTime"] = chat["timestamp"]
        daily_data[date_str]["chats"].append({
            "chatId": str(chat["_id"]),
            "message": chat.get("message", ""),
            "timestamp": chat["timestamp"],
            "sender": chat.get("sender", "User")
        })
        
        # Count messages by sender
        sender = chat.get("sender", "User")
        if sender.lower() == "user":
            daily_data[date_str]["userMessages"] += 1
        else:
            daily_data[date_str]["botMessages"] += 1
    
    # Calculate proper session-based duration for each day
    for date_str in daily_data:
        day_data = daily_data[date_str]
        day_chats = day_data["chats"]
        
        if len(day_chats) <= 1:
            day_data["durationMinutes"] = 0
            continue
        
        # Group chats into sessions based on time gaps (similar to session analytics)
        session_gap_seconds = 30 * 60  # 30 minutes gap
        sessions = []
        current_session = [day_chats[0]]
        
        for i in range(1, len(day_chats)):
            current_chat_time = parse_timestamp(day_chats[i]["timestamp"])
            prev_chat_time = parse_timestamp(day_chats[i-1]["timestamp"])
            time_gap = (current_chat_time - prev_chat_time).total_seconds()
            
            if time_gap <= session_gap_seconds:
                current_session.append(day_chats[i])
            else:
                sessions.append(current_session)
                current_session = [day_chats[i]]
        
        # Add the last session
        if current_session:
            sessions.append(current_session)
        
        # Calculate total duration from all sessions
        total_duration = 0
        for session in sessions:
            if len(session) > 1:
                session_start = parse_timestamp(session[0]["timestamp"])
                session_end = parse_timestamp(session[-1]["timestamp"])
                session_duration = (session_end - session_start).total_seconds() / 60
                total_duration += session_duration
        
        day_data["durationMinutes"] = round(total_duration, 2)
        
        # Store session information for categorization
        day_data["sessions"] = sessions
    
    # Get user's full session data for categorization mapping
    user_session_data = calculate_user_sessions(user_id, 30)
    
    # Convert to list and sort by date
    daily_analytics = []
    for date_str in sorted(daily_data.keys()):
        day_data = daily_data[date_str]
        
        # Map day sessions to user sessions for categorization
        day_sessions_for_categorization = []
        for session_idx, session in enumerate(user_session_data.get("sessions", [])):
            session_date = parse_timestamp(session["startTime"]).date().strftime('%Y-%m-%d')
            if session_date == date_str:
                day_sessions_for_categorization.append({
                    "session_id": session["sessionId"],
                    "categorization": session.get("categorization", {})
                })
        
        # Get categorization for this day
        day_categorization = get_day_categorization(user_id, date_str, day_sessions_for_categorization)
        
        # Add categorization to day data
        day_data["categorization"] = {
            "primary_category": day_categorization["primary_category"],
            "sub_category": day_categorization["sub_category"]
        }
        
        daily_analytics.append(day_data)
    
    # Calculate summary statistics
    total_chats = sum(day["chatCount"] for day in daily_analytics)
    total_duration = sum(day["durationMinutes"] for day in daily_analytics)
    active_days = len(daily_analytics)
    avg_chats_per_day = total_chats / active_days if active_days > 0 else 0
    avg_duration_per_day = total_duration / active_days if active_days > 0 else 0
    
    return {
        "userId": user_id,
        "dateRange": {
            "startDate": start_date.strftime('%Y-%m-%d'),
            "endDate": end_date.strftime('%Y-%m-%d'),
            "totalDays": (end_date - start_date).days + 1
        },
        "summary": {
            "totalChats": total_chats,
            "totalDurationMinutes": round(total_duration, 2),
            "activeDays": active_days,
            "avgChatsPerDay": round(avg_chats_per_day, 2),
            "avgDurationPerDay": round(avg_duration_per_day, 2)
        },
        "dailyAnalytics": daily_analytics
    }

@user_analytics_bp.route('/day-wise-analytics', methods=['GET'])
def get_user_day_wise_analytics():
    """
    Get day-wise analytics for a specific user with filtering options
    Query params:
    - user_id: required - specific user ID
    - filter: week/month/custom (default: month)
    - start_date: YYYY-MM-DD format (for custom filter)
    - end_date: YYYY-MM-DD format (for custom filter)
    - include_chats: include detailed chat information for each day (default: false)
    - primary_category: filter by primary category (optional)
    - sub_category: filter by sub category (optional)
    """
    
    try:
        user_id = request.args.get('user_id')
        filter_type = request.args.get('filter', 'month')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        include_chats = request.args.get('include_chats', 'false').lower() == 'true'
        primary_category_filter = request.args.get('primary_category')
        sub_category_filter = request.args.get('sub_category')
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        # Check if user exists
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Calculate date range based on filter
        end_date = datetime.now()
        
        if filter_type == 'week':
            start_date = end_date - timedelta(days=7)
        elif filter_type == 'month':
            start_date = end_date - timedelta(days=30)
        elif filter_type == 'custom':
            if not start_date_str or not end_date_str:
                return jsonify({"error": "start_date and end_date are required for custom filter"}), 400
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        else:
            return jsonify({"error": "Invalid filter type. Use 'week', 'month', or 'custom'"}), 400
        
        # Get day-wise analytics
        if include_chats:
            analytics_data = calculate_user_day_wise_analytics_with_chats(user_id, start_date, end_date)
        else:
            analytics_data = calculate_user_day_wise_analytics(user_id, start_date, end_date)
        
        # Apply category filters if provided
        if primary_category_filter or sub_category_filter:
            filtered_daily_analytics = []
            for day in analytics_data["dailyAnalytics"]:
                categorization = day.get("categorization", {})
                
                # Check primary category filter
                if primary_category_filter:
                    if categorization.get("primary_category", "").lower() != primary_category_filter.lower():
                        continue
                
                # Check sub category filter
                if sub_category_filter:
                    if categorization.get("sub_category", "").lower() != sub_category_filter.lower():
                        continue
                
                filtered_daily_analytics.append(day)
            
            # Recalculate summary statistics for filtered data
            total_chats = sum(day["chatCount"] for day in filtered_daily_analytics)
            total_duration = sum(day["durationMinutes"] for day in filtered_daily_analytics)
            active_days = len(filtered_daily_analytics)
            avg_chats_per_day = total_chats / active_days if active_days > 0 else 0
            avg_duration_per_day = total_duration / active_days if active_days > 0 else 0
            
            # Update analytics data with filtered results
            analytics_data["dailyAnalytics"] = filtered_daily_analytics
            analytics_data["summary"] = {
                "totalChats": total_chats,
                "totalDurationMinutes": round(total_duration, 2),
                "activeDays": active_days,
                "avgChatsPerDay": round(avg_chats_per_day, 2),
                "avgDurationPerDay": round(avg_duration_per_day, 2)
            }
        
        # Add user information
        analytics_data.update({
            "userName": user.get("userName"),
            "mobileNumber": user.get("mobileNumber"),
            "age": user.get("age"),
            "gender": user.get("gender"),
            "createdAt": user.get("createdAt"),
            "lastActiveAt": user.get("lastActiveAt")
        })
        
        return jsonify({
            "success": True,
            "filter": filter_type,
            "includeChats": include_chats,
            "categoryFilters": {
                "primary_category": primary_category_filter,
                "sub_category": sub_category_filter
            },
            "data": analytics_data
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500