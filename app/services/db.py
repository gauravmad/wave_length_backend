from pymongo import MongoClient
from app.config import Config

try:
    mongo_client = MongoClient(Config.MONGO_CONNECTION_STRING)
    db = mongo_client["database"]  # ← your database name
    print("✅ MongoDB Connected Successfully", Config.MONGO_CONNECTION_STRING);
except Exception as e:
    print("❌ MongoDB Connection Failed:", e)
    db = None
