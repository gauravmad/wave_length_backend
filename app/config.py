import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    MONGO_CONNECTION_STRING  = os.getenv("MONGO_CONNECTION_STRING")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY")
    NOVU_API_KEY= os.getenv("NOVU_API_KEY")
    NOVU_TRIGGER_URL=os.getenv("NOVU_TRIGGER_URL")
    SUBSCRIBER_ID=os.getenv("SUBSCRIBER_ID")
    SECRET_KEY=os.getenv("SECRET_KEY")