import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    MONGO_CONNECTION_STRING  = os.getenv("MONGO_CONNECTION_STRING")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
