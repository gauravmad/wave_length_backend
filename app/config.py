# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration with Qdrant support"""
    
    # Existing configuration
    MONGO_CONNECTION_STRING = os.getenv("MONGO_CONNECTION_STRING")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    NOVU_API_KEY = os.getenv("NOVU_API_KEY")
    NOVU_TRIGGER_URL = os.getenv("NOVU_TRIGGER_URL")
    SUBSCRIBER_ID = os.getenv("SUBSCRIBER_ID")
    SECRET_KEY = os.getenv("SECRET_KEY")
    AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")
    AWS_ACCESS_KEY_ID = AWS_ACCESS_KEY
    BEDROCK_MODEL_ARN = os.getenv('BEDROCK_MODEL_ARN')
    AZURE_SUBSCRIPTION_KEY = os.getenv("AZURE_SUBSCRIPTION_KEY")

    # Qdrant Configuration (fixed variable names)
    VECTOR_STORE_PROVIDER = os.getenv('VECTOR_STORE_PROVIDER', 'qdrant')
    QDRANT_URL = os.getenv('QUADRANT_API_URL')  # Note: using QUADRANT_API_URL from your env
    QDRANT_API_KEY = os.getenv('QUADRANT_API_KEY')  # Note: using QUADRANT_API_KEY from your env
    
    # Memory settings
    MEM0_COLLECTION_NAME = os.getenv('MEM0_COLLECTION_NAME', 'chat_memories')
    
    @classmethod
    def validate_qdrant_config(cls) -> None:
        """Validate Qdrant configuration"""
        missing_configs = []
        
        if not cls.QDRANT_URL:
            missing_configs.append('QUADRANT_API_URL')
        
        # API key is optional for local Qdrant instances
        if not cls.QDRANT_API_KEY and not cls.QDRANT_URL.startswith('http://localhost') and not cls.QDRANT_URL.startswith('http://127.0.0.1') and not '15.207.106.82' in cls.QDRANT_URL:
            print("⚠️  Warning: No API key provided. This is fine for local Qdrant instances.")
        
        if not cls.ANTHROPIC_API_KEY:  # Changed to use Anthropic instead of Gemini
            missing_configs.append('ANTHROPIC_API_KEY')
        
        if missing_configs:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing_configs)}. "
                f"Please set these environment variables."
            )
        
        # Validate URL format
        if not cls.QDRANT_URL.startswith(('http://', 'https://')):
            raise ValueError("QUADRANT_API_URL must start with http:// or https://")
        
        print(f"✅ Qdrant configuration validated: {cls.QDRANT_URL}")
        if cls.QDRANT_API_KEY:
            print(f"✅ Qdrant API key validated")
        else:
            print(f"✅ Local Qdrant instance (no API key required)")
        print(f"✅ Anthropic API key validated")
    
    @classmethod
    def validate_anthropic_config(cls) -> None:
        """Validate Anthropic configuration"""
        if not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        print("✅ Anthropic configuration validated")
    
    @classmethod
    def get_qdrant_info(cls) -> dict:
        """Get Qdrant configuration info (without sensitive data)"""
        return {
            "url": cls.QDRANT_URL,
            "collection_name": cls.MEM0_COLLECTION_NAME,
            "api_key_set": bool(cls.QDRANT_API_KEY),
            "gemini_key_set": bool(cls.GEMINI_API_KEY)
        }