import traceback
from bson import ObjectId
from typing import Dict, Optional

from app.services.db import db
from app.memory.memory_service import MemoryService
from app.utility.image_service import ImageService
from app.system_prompt.prompt_service import PromptService
from app.utility.token_service import TokenService
from app.services.gemini import GeminiService
from app.utility.performance_logger import PerformanceLogger
from app.utility.claude_reply import fetch_recent_chats
from app.socket.controller.chat_controller import save_ai_message

class ChatService:
    """Main service class for handling chat operations"""
    
    def __init__(self):
        self.memory_service = MemoryService()
        self.image_service = ImageService()
        self.prompt_service = PromptService()
        self.token_service = TokenService()
        self.gemini_service = GeminiService()
    
    def _get_user_from_db(self, user_id: str) -> Optional[Dict]:
        """Fetch user from database"""
        try:
            try:
                user_object_id = ObjectId(user_id)
                user = db.users.find_one({"_id": user_object_id})
            except:
                user = db.users.find_one({"_id": user_id})
            return user
        except Exception as e:
            print(f"❌ Failed to fetch user: {e}")
            return None
    
    def get_claude_reply(
        self, 
        prompt: str, 
        user_id: str, 
        character_name: str, 
        character_id: str, 
        image_url: Optional[str] = None
    ) -> Dict:
        """Main method to get AI reply with memory integration"""
        
        logger = PerformanceLogger()
        
        try:
            # --- Fetch user ---
            user = self._get_user_from_db(user_id)
            logger.log_step("Fetch user from DB")
            
            # --- Load system prompt ---
            system_prompt = self.prompt_service.load_system_prompt(character_name, user)
            logger.log_step("Load and process system prompt")
            
            # --- STEP 1: Add current user message to memory ---
            self.memory_service.add_message_to_memory(user_id, character_id, prompt, "User")
            logger.log_step("Add user message to memory")
            
            # --- STEP 2: Search for relevant memories ---
            relevant_memories = self.memory_service.search_relevant_memories(
                user_id, character_id, prompt, limit=15
            )
            logger.log_step("Search relevant memories")
            
            # --- STEP 3: Fetch recent chats ---
            recent_chats_text = fetch_recent_chats(user_id, character_id, limit=20)
            logger.log_step("Fetch recent chats")
            
            # --- Inject context into system prompt ---
            memory_context = relevant_memories or "No relevant memories found."
            chats_context = recent_chats_text or "No recent chats available."
            
            system_prompt = self.prompt_service.inject_context_into_prompt(
                system_prompt, memory_context, chats_context
            )
            logger.log_step("Inject memory and chat context")
            
            # --- Token budgeting ---
            token_info = self.token_service.calculate_token_budget(system_prompt, prompt)
            logger.log_step("Token count + budgeting")
            
            # --- Handle truncation if needed ---
            if token_info["needs_truncation"]:
                memory_context, chats_context, system_prompt = self.token_service.truncate_context(
                    memory_context, chats_context, system_prompt, token_info["remaining_budget"]
                )
                token_info = self.token_service.calculate_token_budget(system_prompt, prompt)
            logger.log_step("Truncate context if needed")
            
            # --- Process image if provided ---
            image_data = None
            if image_url:
                image_data = self.image_service.download_and_process_image(image_url)
                if not image_data:
                    print(f"⚠️ Warning: Failed to process image from {image_url}")
            logger.log_step("Process image" if image_url else "Skip image processing")
            
            # --- Generate AI response ---
            full_prompt = f"{system_prompt}\n\nUser: {prompt}"
            ai_reply = self.gemini_service.generate_response(
                full_prompt, 
                image_data, 
                max_output_tokens=self.token_service.RESERVED_OUTPUT_TOKENS
            )
            logger.log_step("Gemini API call")
            
            # --- Process AI reply ---
            ai_tokens = self.token_service.safe_token_count(ai_reply)
            logger.log_step("Process AI reply")
            
            # --- STEP 4: Add AI response to memory ---
            self.memory_service.add_message_to_memory(user_id, character_id, ai_reply, "AI")
            logger.log_step("Add AI response to memory")
            
            # --- STEP 5: Update memory with conversation context ---
            self.memory_service.update_memory_from_conversation(user_id, character_id, prompt, ai_reply)
            logger.log_step("Update memory with conversation")
            
            # --- Save AI message ---
            ai_message_data = save_ai_message(user_id, character_id, ai_reply)
            logger.log_step("Save AI message to DB")
            
            # --- Calculate memory stats ---
            memory_stats = self.memory_service.get_memory_stats(user_id, character_id)
            relevant_memories_count = (
                len(relevant_memories.split('\n')) - 1 
                if relevant_memories != "No relevant memories found." 
                else 0
            )
            
            return {
                "success": True,
                "message": ai_reply,
                "timestamp": ai_message_data["timestamp"],
                "tokens": {
                    "system_prompt": token_info["system_tokens"],
                    "user_prompt": token_info["prompt_tokens"],
                    "memory_context": self.token_service.safe_token_count(memory_context),
                    "recent_chats": self.token_service.safe_token_count(chats_context),
                    "output": ai_tokens,
                    "total_used": token_info["system_tokens"] + token_info["prompt_tokens"] + ai_tokens
                },
                "userId": str(user_id),
                "characterId": str(character_id),
                "timings": logger.get_timings(),
                "memory_stats": {
                    "relevant_memories_count": relevant_memories_count,
                    "total_memories": memory_stats.get("total_memories", 0)
                }
            }
            
        except Exception as e:
            traceback.print_exc()
            error_message = "⚠️ Sorry, I'm having trouble responding right now."
            detailed_error = f"{error_message}\n\nError: {str(e)}"
            
            error_message_data = save_ai_message(user_id, character_id, error_message)
            logger.log_step("Error handling")
            
            return {
                "success": False,
                "message": detailed_error,
                "timestamp": error_message_data["timestamp"],
                "userId": str(user_id),
                "characterId": str(character_id),
                "error": str(e),
                "timings": logger.get_timings()
            }


# Factory function to maintain backward compatibility
def get_claude_reply(
    prompt: str, 
    user_id: str, 
    character_name: str, 
    character_id: str,
    image_url: Optional[str] = None
) -> Dict:
    """Factory function to maintain backward compatibility with existing code"""
    chat_service = ChatService()
    return chat_service.get_claude_reply(prompt, user_id, character_name, character_id, image_url)