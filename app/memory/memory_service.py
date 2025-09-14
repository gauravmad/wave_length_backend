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
    
    def search_relevant_memories(self, user_id: str, character_id: str, query: str, limit: int = 15) -> str:
        """Search for relevant memories based on the current query with improved relevance"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            
            # Enhanced query for better relevance - include context keywords
            enhanced_query = f"{query} conversation context user preferences"
            
            # Search for relevant memories with enhanced query
            relevant_memories = self.memory.search(
                query=enhanced_query,
                user_id=user_identifier,
                limit=limit
            )
            
            # print(f"🔍 Raw search results type: {type(relevant_memories)}")
            # print(f"🔍 Raw search results: {relevant_memories}")
            
            if not relevant_memories:
                print(f"🔍 No relevant memories found for query: {query[:50]}...")
                return "No relevant memories found."
            
            # Handle different return formats from Mem0
            # Check if it's a dictionary with 'results' key (new format)
            if isinstance(relevant_memories, dict) and 'results' in relevant_memories:
                results_list = relevant_memories['results']
                if not results_list:
                    print(f"🔍 No results in search response for query: {query[:50]}...")
                    return "No relevant memories found."
                
                # Filter memories by relevance score (only include memories with score > 0.3)
                filtered_memories = [mem for mem in results_list if mem.get('score', 0) > 0.3]
                
                if not filtered_memories:
                    print(f"🔍 No high-relevance memories found (score > 0.3) for query: {query[:50]}...")
                    return "No relevant memories found."
                
                # Format memories for context - prioritize by relevance score
                memory_context = "## Relevant Memories:\n"
                for i, mem in enumerate(filtered_memories[:10], 1):  # Limit to top 10 most relevant
                    memory_text = mem.get('memory', '')
                    
                    # Clean up memory text
                    if memory_text.startswith(('User:', 'AI:')):
                        memory_text = memory_text.split(':', 1)[1].strip()
                    
                    memory_context += f"{i}. {memory_text}\n"
                
                print(f"🔍 Found {len(filtered_memories)} relevant memories (score > 0.3) for query: {query[:50]}...")
                return memory_context
            
            # Handle list format (legacy)
            elif isinstance(relevant_memories, list):
                # If it's a list of strings, use them directly
                if relevant_memories and isinstance(relevant_memories[0], str):
                    memory_context = "## Relevant Memories:\n"
                    for i, memory_text in enumerate(relevant_memories[:10], 1):
                        # Clean up memory text
                        if memory_text.startswith(('User:', 'AI:')):
                            memory_text = memory_text.split(':', 1)[1].strip()
                        memory_context += f"{i}. {memory_text}\n"
                    
                    print(f"🔍 Found {len(relevant_memories)} relevant memories for query: {query[:50]}...")
                    return memory_context
                
                # If it's a list of dictionaries, process them
                elif relevant_memories and isinstance(relevant_memories[0], dict):
                    # Filter memories by relevance score (only include memories with score > 0.3)
                    filtered_memories = [mem for mem in relevant_memories if mem.get('score', 0) > 0.3]
                    
                    if not filtered_memories:
                        print(f"🔍 No high-relevance memories found (score > 0.3) for query: {query[:50]}...")
                        return "No relevant memories found."
                    
                    # Format memories for context - prioritize by relevance score
                    memory_context = "## Relevant Memories:\n"
                    for i, mem in enumerate(filtered_memories[:10], 1):  # Limit to top 10 most relevant
                        memory_text = mem.get('memory', '')
                        
                        # Clean up memory text
                        if memory_text.startswith(('User:', 'AI:')):
                            memory_text = memory_text.split(':', 1)[1].strip()
                        
                        memory_context += f"{i}. {memory_text}\n"
                    
                    print(f"🔍 Found {len(filtered_memories)} relevant memories (score > 0.3) for query: {query[:50]}...")
                    return memory_context
            
            # If it's a single string, return it
            elif isinstance(relevant_memories, str):
                memory_context = "## Relevant Memories:\n"
                if relevant_memories.startswith(('User:', 'AI:')):
                    relevant_memories = relevant_memories.split(':', 1)[1].strip()
                memory_context += f"1. {relevant_memories}\n"
                print(f"🔍 Found 1 relevant memory for query: {query[:50]}...")
                return memory_context
            
            print(f"🔍 Unexpected memory format: {type(relevant_memories)}")
            return "No relevant memories found."
            
        except Exception as e:
            print(f"❌ Failed to search memories: {e}")
            return "No memories available."
    
    def update_memory_from_conversation(self, user_id: str, character_id: str, user_message: str, ai_response: str) -> bool:
        """Update memories based on new conversation turn"""
        try:
            user_identifier = self.get_user_identifier(user_id, character_id)
            
            # Update memories with the conversation context
            conversation_context = f"User: {user_message}\nAI: {ai_response}"
            
            # Use the correct method call for Mem0 update
            self.memory.update(
                message=conversation_context,
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
