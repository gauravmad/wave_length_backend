import traceback
from bson import ObjectId
from typing import Dict, Optional

from app.services.db import db
from app.memory.memory_service import MemoryService
from app.utility.image_service import ImageService
from app.system_prompt.prompt_service import PromptService
from app.utility.token_service import TokenService
from app.services.gemini import GeminiService
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
        
        try:
            print(f"🚀 Starting chat for user {user_id} with character {character_name}")
            
            # --- Fetch user ---
            user = self._get_user_from_db(user_id)
            print(f"✅ User fetched: {user.get('userName', 'Unknown') if user else 'Not found'}")
            
            # --- Load system prompt ---
            system_prompt = self.prompt_service.load_system_prompt(character_name, user)
            print(f"✅ System prompt loaded for character: {character_name}")
            
            # --- STEP 1: Search for relevant memories (no summary, only relevant context) ---
            relevant_memories = self.memory_service.search_relevant_memories(
                user_id, character_id, prompt, limit=15
            )
            print(f"🔍 Memory search completed")
            
            # Log the memory context that will be fed to LLM
            print("=" * 80)
            print("🧠 MEMORY CONTEXT BEING FED TO LLM:")
            if relevant_memories and relevant_memories != "No relevant memories found.":
                print(relevant_memories)
            else:
                print("No relevant memories found - using only recent chat context")
            print("=" * 80)
            
            # --- STEP 3: Fetch recent chats (limited to 20) ---
            recent_chats_text = fetch_recent_chats(user_id, character_id, limit=20)
            print(f"📝 Recent chats fetched (limit: 20)")
            
            # --- STEP 4: Create timestamp info for context ---
            from datetime import datetime
            current_time = datetime.now()
            
            # Get the last message timestamp from recent chats
            last_message_time = None
            if recent_chats_text:
                # Extract timestamp from the most recent message
                lines = recent_chats_text.split('\n')
                for line in reversed(lines):
                    if ']' in line and '[' in line:
                        try:
                            # Extract timestamp from format like "[2025-09-12 17:49:27] user: message"
                            timestamp_str = line.split(']')[0].replace('[', '')
                            last_message_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            break
                        except:
                            continue
            
            # Format current time
            current_formatted = current_time.strftime('%d %B %Y, %I:%M%p (%A)')
            
            # Format previous message time or use current time if no previous message
            if last_message_time:
                previous_formatted = last_message_time.strftime('%d %B %Y, %I:%M%p (%A)')
                
                # Calculate time gap
                time_diff = current_time - last_message_time
                days = time_diff.days
                hours = time_diff.seconds // 3600
                minutes = (time_diff.seconds % 3600) // 60
                
                # Format time gap
                if days > 0:
                    time_gap = f"{days} days, {hours} hours"
                elif hours > 0:
                    time_gap = f"0 days, {hours} hours"
                else:
                    time_gap = f"0 days, 0 hours"
                
                # Determine if it's today or not
                current_date = current_time.date()
                last_date = last_message_time.date()
                
                if current_date == last_date:
                    previous_suffix = " - Today"
                    current_suffix = " - Now"
                else:
                    previous_suffix = ""
                    current_suffix = " - Now"
                
                timestamp_info = f"Previous message timing: {previous_formatted}{previous_suffix}\nCurrent message timing: {current_formatted}{current_suffix}\nTime gap: {time_gap}"
            else:
                # No previous message, just current time
                timestamp_info = f"Previous message timing: No previous messages\nCurrent message timing: {current_formatted} - Now\nTime gap: First message"
            
            print(f"🕐 Timestamp info created: {timestamp_info}")
            
            # --- STEP 5: Inject all context into system prompt ---
            memory_context = relevant_memories if relevant_memories != "No relevant memories found." else ""
            chats_context = recent_chats_text or ""
            
            # Inject all template variables
            system_prompt = self.prompt_service.inject_all_context_into_prompt(
                system_prompt, memory_context, chats_context, timestamp_info
            )
            print(f"✅ All context variables injected into system prompt")
            
            # Log the populated template variables
            print("=" * 80)
            print("📋 TEMPLATE VARIABLES POPULATED:")
            print("=" * 80)
            print(f"{{userName}}: {user.get('userName', 'bestie') if user else 'bestie'}")
            print(f"{{gender}}: {user.get('gender', '') if user else ''}")
            print(f"{{age}}: {user.get('age', '') if user else ''}")
            print(f"{{mobileNumber}}: {user.get('mobileNumber', '') if user else ''}")
            print(f"{{conversationSummary}}: {'Memory context loaded' if memory_context else 'No memory context'}")
            print(f"{{recentMessages}}: {'Recent chats loaded' if chats_context else 'No recent chats'}")
            print(f"{{timestampInfo}}: {timestamp_info}")
            print("=" * 80)
            
            # --- Token budgeting ---
            token_info = self.token_service.calculate_token_budget(system_prompt, prompt)
            total_tokens = token_info['system_tokens'] + token_info['prompt_tokens']
            print(f"📊 Token budget calculated: {total_tokens} tokens (system: {token_info['system_tokens']}, prompt: {token_info['prompt_tokens']})")
            
            # --- Handle truncation if needed ---
            if token_info["needs_truncation"]:
                memory_context, chats_context, system_prompt = self.token_service.truncate_context(
                    memory_context, chats_context, system_prompt, token_info["remaining_budget"]
                )
                token_info = self.token_service.calculate_token_budget(system_prompt, prompt)
                print(f"✂️ Context truncated to fit token budget")
            
            # --- Process image if provided ---
            image_data = None
            if image_url:
                image_data = self.image_service.download_and_process_image(image_url)
                if not image_data:
                    print(f"⚠️ Warning: Failed to process image from {image_url}")
                else:
                    print(f"🖼️ Image processed successfully")
            
            # --- Generate AI response ---
            full_prompt = f"{system_prompt}\n\nUser: {prompt}"
            ai_reply = self.gemini_service.generate_response(
                full_prompt, 
                image_data, 
                max_output_tokens=self.token_service.RESERVED_OUTPUT_TOKENS
            )
            print(f"🤖 AI response generated: {ai_reply[:50]}...")
            
            # --- Process AI reply ---
            ai_tokens = self.token_service.safe_token_count(ai_reply)
            
            # --- STEP 4: Add AI response to memory ---
            self.memory_service.add_message_to_memory(user_id, character_id, ai_reply, "AI")
            print(f"💾 AI response added to memory")
            
            # --- STEP 5: Update memory with conversation context ---
            self.memory_service.update_memory_from_conversation(user_id, character_id, prompt, ai_reply)
            print(f"🔄 Memory updated with conversation context")
            
            # --- Save AI message ---
            ai_message_data = save_ai_message(user_id, character_id, ai_reply)
            print(f"💾 AI message saved to database")
            
            # --- Calculate memory stats ---
            memory_stats = self.memory_service.get_memory_stats(user_id, character_id)
            relevant_memories_count = (
                len(memory_context.split('\n')) - 1 
                if memory_context and memory_context != "No relevant memories found." 
                else 0
            )
            
            print(f"✅ Chat completed successfully")
            
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
                "memory_stats": {
                    "relevant_memories_count": relevant_memories_count,
                    "total_memories": memory_stats.get("total_memories", 0)
                }
            }
            
        except Exception as e:
            traceback.print_exc()
            error_message = "⚠️ Sorry, I'm having trouble responding right now."
            detailed_error = f"{error_message}\n\nError: {str(e)}"
            
            print(f"❌ Error in chat processing: {str(e)}")
            
            error_message_data = save_ai_message(user_id, character_id, error_message)
            
            return {
                "success": False,
                "message": detailed_error,
                "timestamp": error_message_data["timestamp"],
                "userId": str(user_id),
                "characterId": str(character_id),
                "error": str(e)
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