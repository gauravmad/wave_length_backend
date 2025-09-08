from datetime import datetime
from bson import ObjectId
from typing import List, Dict, Optional
from app.config import Config

from app.services.db import db
from app.memory.mem0ai_config import MemoryConfig

class MemoryService:
    """Service class for handling memory operations"""
    
    def __init__(self):
        self.memory = MemoryConfig.initialize_memory()
    
    @staticmethod
    def get_user_identifier(user_id: str, character_id: str) -> str:
        """Create a unique identifier for user-character pair"""
        return f"user_{user_id}_char_{character_id}"
    
    def _get_user_info(self, user_id: str) -> Optional[Dict]:
        """Get user information from database"""
        try:
            try:
                user_object_id = ObjectId(user_id)
                user = db.users.find_one({"_id": user_object_id})
            except:
                user = db.users.find_one({"_id": user_id})
            return user
        except Exception as e:
            print(f"❌ Failed to fetch user info: {e}")
            return None
    
    def add_message_to_memory(self, user_id: str, character_id: str, message: str, sender: str) -> bool:
        """Add memory from a chat message"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            user = self._get_user_info(user_id)
            user_name = user.get("userName", "User") if user else "User"
            
            # Add context about who said what
            contextual_message = f"{sender}: {message}"
            
            # Add memory with metadata
            self.memory.add(
                messages=contextual_message,
                user_id=user_identifier,
                metadata={
                    "user_id": user_id,
                    "character_id": character_id,
                    "user_name": user_name,
                    "sender": sender,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_type": "chat"
                }
            )
            
            print(f"💾 Memory added for {sender}: {message[:100]}...")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add memory: {e}")
            return False
    
    def search_relevant_memories(self, user_id: str, character_id: str, query: str, limit: int = 10) -> str:
        """Search for relevant memories based on the current query"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            
            # Search for relevant memories
            relevant_memories = self.memory.search(
                query=query,
                user_id=user_identifier,
                limit=limit
            )
            
            if not relevant_memories:
                return "No relevant memories found."
            
            # Format memories for context
            memory_context = "## Relevant Memories:\n"
            for i, mem in enumerate(relevant_memories, 1):
                memory_text = mem.get('memory', '')
                score = mem.get('score', 0)
                metadata = mem.get('metadata', {})
                
                # Add timestamp if available
                timestamp = metadata.get('timestamp', 'Unknown time')
                memory_context += f"{i}. {memory_text} (Relevance: {score:.2f}, Time: {timestamp})\n"
            
            print(f"🔍 Found {len(relevant_memories)} relevant memories")
            return memory_context
            
        except Exception as e:
            print(f"❌ Failed to search memories: {e}")
            return "No memories available."
    
    def update_memory_from_conversation(self, user_id: str, character_id: str, user_message: str, ai_response: str) -> bool:
        """Update memories based on new conversation turn"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            
            # Update memories with the conversation context
            conversation_context = f"User: {user_message}\nAI: {ai_response}"
            
            self.memory.update(
                messages=conversation_context,
                user_id=user_identifier
            )
            
            print(f"🔄 Memory updated with conversation context")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update memory: {e}")
            return False
    
    def get_all_memories_for_user(self, user_id: str, character_id: str) -> List[Dict]:
        """Get all memories for a user-character pair"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            memories = self.memory.get_all(user_id=user_identifier)
            return memories
            
        except Exception as e:
            print(f"❌ Failed to get all memories: {e}")
            return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory"""
        try:
            self.memory.delete(memory_id=memory_id)
            print(f"🗑️ Memory {memory_id} deleted")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delete memory: {e}")
            return False
    
    def get_memory_stats(self, user_id: str, character_id: str) -> Dict:
        """Get memory statistics for debugging"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            all_memories = self.memory.get_all(user_id=user_identifier)
            
            return {
                "total_memories": len(all_memories),
                "user_identifier": user_identifier
            }
        except Exception as e:
            print(f"❌ Failed to get memory stats: {e}")
            return {"total_memories": 0, "error": str(e)}
    
    def reset_user_memories(self, user_id: str, character_id: str) -> bool:
        """Reset all memories for a specific user-character pair"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            all_memories = self.memory.get_all(user_id=user_identifier)
            
            for mem in all_memories:
                if 'id' in mem:
                    self.memory.delete(memory_id=mem['id'])
            
            print(f"🔄 Reset all memories for user {user_identifier}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to reset memories: {e}")
            return False
    
    def migrate_existing_summaries_to_mem0(self) -> bool:
        """
        One-time migration function to convert existing summaries to Mem0 memories
        Call this once to migrate your existing data
        """
        try:
            summaries = db.summaries.find({})
            
            for summary in summaries:
                user_id = summary.get("userId")
                character_id = summary.get("characterId")
                summary_text = summary.get("summary", "")
                
                if user_id and character_id and summary_text:
                    user_identifier = self.get_user_identifier(user_id, character_id)
                    
                    # Add the old summary as initial memory
                    self.memory.add(
                        messages=f"Previous conversation summary: {summary_text}",
                        user_id=user_identifier,
                        metadata={
                            "user_id": user_id,
                            "character_id": character_id,
                            "message_type": "migrated_summary",
                            "timestamp": summary.get("updatedAt", datetime.utcnow()).isoformat(),
                            "migration_date": datetime.utcnow().isoformat()
                        }
                    )
                    
                    print(f"📦 Migrated summary for user {user_id}, character {character_id}")
            
            print("✅ Migration completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False
    
    def test_memory_system(self, user_id: str, character_id: str) -> None:
        """Test the memory system with sample data"""
        print("🧪 Testing Mem0 integration...")
        
        # Test adding memories
        self.add_message_to_memory(user_id, character_id, "I love pizza", "User")
        self.add_message_to_memory(user_id, character_id, "That's great! What's your favorite topping?", "AI")
        self.add_message_to_memory(user_id, character_id, "I prefer pepperoni and mushrooms", "User")
        
        # Test searching memories
        results = self.search_relevant_memories(user_id, character_id, "food preferences", limit=5)
        print("🔍 Search results:", results)
        
        # Test getting stats
        stats = self.get_memory_stats(user_id, character_id)
        print("📊 Memory stats:", stats)
        
        print("✅ Memory system test completed")


    def recreate_collection_for_gemini(self):
        """Recreate Qdrant collection with 768 dimensions for Gemini embeddings"""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from app.config import Config
        
        client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,
        )
        
        # Delete existing collection
        try:
            client.delete_collection(Config.MEM0_COLLECTION_NAME)
            print(f"🗑️ Deleted existing collection: {Config.MEM0_COLLECTION_NAME}")
        except Exception as e:
            print(f"Collection might not exist: {e}")
        
        # Create new collection with 768 dimensions (Gemini default)
        client.create_collection(
            collection_name=Config.MEM0_COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print(f"✅ Created new collection with 768 dimensions: {Config.MEM0_COLLECTION_NAME}")
