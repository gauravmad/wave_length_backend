# app/services/memory/config.py
from mem0 import Memory
from app.config import Config

class MemoryConfig:
    """Memory Configuration with Gemini API support"""
    
    @staticmethod
    def get_qdrant_config() -> dict:
        """Get Qdrant configuration (Cloud or Local) with Gemini LLM"""
        try:
            # Validate configuration first
            Config.validate_qdrant_config()
            
            # Build config for vector store
            vector_store_config = {
                "collection_name": Config.MEM0_COLLECTION_NAME,
                "url": Config.QDRANT_URL,
            }
            
            # Only add API key if it's provided (for Qdrant Cloud)
            if Config.QDRANT_API_KEY:
                vector_store_config["api_key"] = Config.QDRANT_API_KEY
            
            return {
                "vector_store": {
                    "provider": "qdrant",
                    "config": vector_store_config
                },
                "llm": {
                    "provider": "gemini",  # Changed to Gemini provider
                    "config": {
                        "model": "gemini-2.0-flash-001",  # Latest stable Gemini model
                        "temperature": 0.1,
                        "api_key": Config.GEMINI_API_KEY  # Changed to Gemini API key
                    }
                },
                "embedder": {
                    "provider": "gemini",  # Use Gemini embeddings
                    "config": {
                        "model": "models/text-embedding-004",
                        "output_dimensionality": 768,  # Gemini embedding-004 uses 768 dimensions
                        "api_key": Config.GEMINI_API_KEY
                    }
                }
            }
            
        except Exception as e:
            print(f"❌ Configuration error: {e}")
            raise
    
    @staticmethod
    def get_fallback_local_config() -> dict:
        """Complete local configuration with Gemini LLM"""
        try:
            return {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "chat_memories_local",
                        "path": "./chroma_db"
                    }
                },
                "llm": {
                    "provider": "gemini",  # Changed to Gemini provider
                    "config": {
                        "model": "gemini-2.0-flash-001",  # Latest stable model
                        "temperature": 0.1,
                        "api_key": Config.GEMINI_API_KEY  # Changed to Gemini API key
                    }
                },
                "embedder": {
                    "provider": "gemini",  # Use Gemini embeddings
                    "config": {
                        "model": "models/text-embedding-004",
                        "output_dimensionality": 768,  # Gemini embedding-004 uses 768 dimensions
                        "api_key": Config.GEMINI_API_KEY  # Explicit API key
                    }
                }
            }
        except Exception as e:
            print(f"❌ Fallback configuration error: {e}")
            raise
    
    @classmethod
    def initialize_memory(cls, use_fallback: bool = False) -> Memory:
        """
        Initialize and return Memory instance with Gemini
        
        Args:
            use_fallback: If True, use local Chroma instead of Qdrant
        
        Returns:
            Memory: Initialized Memory instance
        """
        try:
            if use_fallback:
                print("🔄 Using fallback local Chroma configuration with Gemini...")
                config = cls.get_fallback_local_config()
                memory = Memory.from_config(config)
                print("✅ Local Chroma Memory with Gemini initialized successfully")
            else:
                print("🔄 Initializing Qdrant Memory with Gemini...")
                config = cls.get_qdrant_config()
                memory = Memory.from_config(config)
                print("✅ Qdrant Memory with Gemini initialized successfully")
                
            return memory
            
        except Exception as e:
            if not use_fallback:
                print(f"❌ Qdrant initialization failed: {e}")
                print("🔄 Attempting fallback to local Chroma...")
                try:
                    return cls.initialize_memory(use_fallback=True)
                except Exception as fallback_error:
                    print(f"❌ Fallback also failed: {fallback_error}")
                    raise Exception(f"Both Qdrant and Chroma initialization failed. Qdrant: {e}, Chroma: {fallback_error}")
            else:
                print(f"❌ Failed to initialize Memory with fallback: {e}")
                raise
    
    @classmethod
    def test_connection(cls) -> dict:
        """Test the memory connection with Gemini and return status"""
        try:
            # Test Qdrant first
            try:
                config = cls.get_qdrant_config()
                memory = Memory.from_config(config)
                
                # Try a simple operation to test the connection
                test_user_id = "test_connection_user"
                memory.add("Test connection message", user_id=test_user_id)
                
                # Clean up test data
                all_memories = memory.get_all(user_id=test_user_id)
                for mem in all_memories:
                    if 'id' in mem:
                        memory.delete(memory_id=mem['id'])
                
                return {
                    "status": "success",
                    "provider": "qdrant",
                    "llm": "gemini-2.0-flash-001",
                    "message": "Qdrant connection with Gemini successful"
                }
                
            except Exception as qdrant_error:
                print(f"❌ Qdrant test failed: {qdrant_error}")
                
                # Test fallback
                config = cls.get_fallback_local_config()
                memory = Memory.from_config(config)
                
                # Try a simple operation
                test_user_id = "test_connection_user"
                memory.add("Test connection message", user_id=test_user_id)
                
                # Clean up test data
                all_memories = memory.get_all(user_id=test_user_id)
                for mem in all_memories:
                    if 'id' in mem:
                        memory.delete(memory_id=mem['id'])
                
                return {
                    "status": "success",
                    "provider": "chroma_fallback",
                    "llm": "gemini-2.0-flash-001",
                    "message": "Chroma fallback connection with Gemini successful",
                    "qdrant_error": str(qdrant_error)
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"All memory providers failed with Gemini: {e}"
            }