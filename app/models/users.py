from datetime import datetime
from app.services.db import db
from bson.objectid import ObjectId

def create_user(data):
    now = datetime.utcnow()
    data["createdAt"] = now
    data["updatedAt"] = now
    return db.users.insert_one(data)

def get_all_users():
    users = list(db.users.find())
    for user in users:
        user["_id"] = str(user["_id"])
        user["createdAt"] = user["createdAt"].isoformat() if "createdAt" in user else None
        user["updatedAt"] = user["updatedAt"].isoformat() if "updatedAt" in user else None
    return users

def get_user_by_mobile(mobile_number):
    return db.users.find_one({"mobileNumber": mobile_number})

def update_user(user_id, update_data):
    update_data["updatedAt"] = datetime.utcnow()
    return db.users.update_one(
        {"_id":ObjectId(user_id)},
        {"$set":update_data}
    )