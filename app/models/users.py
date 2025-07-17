from app.services.db import db

def create_user(data):
    return db.users.insert_one(data)

def get_all_users():
    return list(db.users.find())

def get_user_by_mobile(mobile_number):
    return db.users.find_one({"mobileNumber": mobile_number})