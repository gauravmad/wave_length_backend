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