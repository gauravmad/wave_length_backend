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
        
        formatted_session = {
            "sessionId": session_idx + 1,
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "chatCount": len(session_chats),
            "durationMinutes": round(session_duration, 2)
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

@user_analytics_bp.route('/sessions', methods=['GET'])
def get_all_users_sessions():
    """
    API 1: Get all users with their session analysis
    Query params:
    - session_gap: minutes between chats to consider new session (default: 30)
    - user_id: specific user ID (optional)
    """
    
    try:
        session_gap = int(request.args.get('session_gap', 30))
        specific_user_id = request.args.get('user_id')
        
        if specific_user_id:
            # Get specific user data
            user = db.users.find_one({"_id": ObjectId(specific_user_id)})
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            user_session_data = calculate_user_sessions(specific_user_id, session_gap)
            
            # Add user info
            user_session_data.update({
                "userName": user.get("userName"),
                "mobileNumber": user.get("mobileNumber"),
                "age": user.get("age"),
                "gender": user.get("gender")
            })
            
            return jsonify({
                "success": True,
                "data": user_session_data
            })
        
        # Get all users
        users = list(db.users.find())
        all_users_sessions = []
        
        for user in users:
            user_id = str(user["_id"])
            user_session_data = calculate_user_sessions(user_id, session_gap)
            
            # Add user info
            user_session_data.update({
                "userName": user.get("userName"),
                "mobileNumber": user.get("mobileNumber"),
                "age": user.get("age"),
                "gender": user.get("gender")
            })
            
            all_users_sessions.append(user_session_data)
        
        # Sort by total chats descending
        all_users_sessions.sort(key=lambda x: x["totalChats"], reverse=True)
        
        return jsonify({
            "success": True,
            "totalUsers": len(all_users_sessions),
            "sessionGapMinutes": session_gap,
            "data": all_users_sessions
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
