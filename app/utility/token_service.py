# app/services/token/token_service.py
import tiktoken
from typing import Tuple, Dict

class TokenService:
    """Service class for handling token counting and management"""
    
    MAX_TOTAL_TOKENS = 2_000_000
    RESERVED_OUTPUT_TOKENS = 8192
    
    def __init__(self):
        self.enc = tiktoken.get_encoding("cl100k_base")
    
    def safe_token_count(self, text: str) -> int:
        """Safely count tokens in text"""
        try:
            return len(self.enc.encode(text))
        except Exception as e:
            print(f"❌ Error counting tokens: {e}")
            return len(text) // 4  # Rough estimate
    
    def calculate_token_budget(self, system_prompt: str, user_prompt: str) -> Dict:
        """Calculate token usage and remaining budget"""
        system_tokens = self.safe_token_count(system_prompt)
        prompt_tokens = self.safe_token_count(user_prompt)
        
        remaining_budget = (
            self.MAX_TOTAL_TOKENS - 
            system_tokens - 
            prompt_tokens - 
            self.RESERVED_OUTPUT_TOKENS
        )
        
        return {
            "system_tokens": system_tokens,
            "prompt_tokens": prompt_tokens,
            "remaining_budget": remaining_budget,
            "needs_truncation": remaining_budget < 0
        }
    
    def truncate_context(
        self, 
        memory_context: str, 
        chats_context: str, 
        system_prompt: str, 
        remaining_budget: int
    ) -> Tuple[str, str, str]:
        """Truncate context if token budget is exceeded"""
        try:
            memory_tokens = self.enc.encode(memory_context)
            chat_tokens = self.enc.encode(chats_context)
            
            # Calculate how much to truncate
            deficit = abs(remaining_budget)
            target_memory_tokens = max(0, len(memory_tokens) - deficit // 2)
            target_chat_tokens = max(0, len(chat_tokens) - deficit // 2)
            
            # Truncate contexts
            truncated_memory = (
                self.enc.decode(memory_tokens[:target_memory_tokens]) 
                if target_memory_tokens > 0 
                else "Memory context too large to include."
            )
            truncated_chats = (
                self.enc.decode(chat_tokens[:target_chat_tokens]) 
                if target_chat_tokens > 0 
                else "Recent chat history too large to include."
            )
            
            # Update system prompt with truncated contexts
            updated_system_prompt = system_prompt.replace(
                memory_context, f"[Truncated]\n{truncated_memory}"
            ).replace(
                chats_context, f"[Truncated]\n{truncated_chats}"
            )
            
            return truncated_memory, truncated_chats, updated_system_prompt
            
        except Exception as e:
            print(f"❌ Error truncating context: {e}")
            return memory_context, chats_context, system_prompt