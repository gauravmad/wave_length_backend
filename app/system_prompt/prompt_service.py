import os
from typing import Dict, Optional


class PromptService:
    """Service class for handling system prompt operations"""
    
    @staticmethod
    def load_system_prompt(character_name: str, user: Optional[Dict] = None) -> str:
        """Load and process system prompt"""
        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.md")
        
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()

        # Replace user details in system prompt
        if user:
            system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie"))
            system_prompt = system_prompt.replace("{{gender}}", user.get("gender", ""))
            system_prompt = system_prompt.replace("{{age}}", str(user.get("age", "")))
            system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", ""))
        else:
            system_prompt = system_prompt.replace("{{userName}}", "bestie")
            system_prompt = system_prompt.replace("{{gender}}", "")
            system_prompt = system_prompt.replace("{{age}}", "")
            system_prompt = system_prompt.replace("{{mobileNumber}}", "")
        
        return system_prompt
    
    @staticmethod
    def inject_context_into_prompt(system_prompt: str, memory_context: str, chats_context: str) -> str:
        """Inject memory and chat context into system prompt"""
        system_prompt = system_prompt.replace("{{conversationSummary}}", memory_context)
        system_prompt = system_prompt.replace("{{recentMessages}}", chats_context)
        return system_prompt
    
    @staticmethod
    def inject_all_context_into_prompt(system_prompt: str, memory_context: str, chats_context: str, timestamp_info: str) -> str:
        """Inject all context variables into system prompt"""
        system_prompt = system_prompt.replace("{{conversationSummary}}", memory_context)
        system_prompt = system_prompt.replace("{{recentMessages}}", chats_context)
        system_prompt = system_prompt.replace("{{timestampInfo}}", timestamp_info)
        return system_prompt