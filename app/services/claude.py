import os
from datetime import datetime
from bson import ObjectId
import tiktoken

import traceback
from app.services.db import db
from app.socket.controller.chat_controller import save_ai_message
from app.utility.claude_reply import fetch_global_summary,fetch_recent_chats
from app.services.aws_bedrcok import bedrock_claude

# ------------------------- Claude Invocation ------------------------- #
def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str, image_url:str = None) -> dict:
    try:
        try:
            user_object_id = ObjectId(user_id)
            user = db.users.find_one({"_id": user_object_id})
        except:
            user = db.users.find_one({"_id": user_id})

        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.txt")
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()

        system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie") if user else "bestie")
        system_prompt = system_prompt.replace("{{gender}}", user.get("gender", "") if user else "")
        system_prompt = system_prompt.replace("{{age}}", str(user.get("age", "")) if user else "")
        system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", "") if user else "")

        # Fetch memory and recent messages
        summary_text = fetch_global_summary(user_id, character_id)
        recent_chats_text = fetch_recent_chats(user_id, character_id)

        enc = tiktoken.get_encoding("cl100k_base")
        def safe_token_count(text: str) -> int:
            return len(enc.encode(text))

        summary_final = summary_text or "No previous conversation history available."
        chats_final = recent_chats_text or "No recent chats available."

        # Insert both into system prompt
        system_prompt = system_prompt.replace("{{conversationSummary}}", summary_final)
        system_prompt = system_prompt.replace("{{recentMessages}}", chats_final)

        # Token budgeting
        MAX_TOTAL_TOKENS = 200_000
        RESERVED_OUTPUT_TOKENS = 4096

        system_tokens = safe_token_count(system_prompt)
        prompt_tokens = safe_token_count(prompt)
        remaining_budget = MAX_TOTAL_TOKENS - system_tokens - prompt_tokens - RESERVED_OUTPUT_TOKENS

        if remaining_budget < 0:
            summary_tokens = enc.encode(summary_text)
            chat_tokens = enc.encode(recent_chats_text)

            target_summary_tokens = max(0, len(summary_tokens) - abs(remaining_budget) // 2)
            target_chat_tokens = max(0, len(chat_tokens) - abs(remaining_budget) // 2)

            truncated_summary = enc.decode(summary_tokens[:target_summary_tokens]) if target_summary_tokens > 0 else "Summary too large to include."
            truncated_chats = enc.decode(chat_tokens[:target_chat_tokens]) if target_chat_tokens > 0 else "Recent chat history too large to include."

            system_prompt = system_prompt.replace(summary_final, f"[Truncated]\n{truncated_summary}")
            system_prompt = system_prompt.replace(chats_final, f"[Truncated]\n{truncated_chats}")
            system_tokens = safe_token_count(system_prompt)


        bedrock_response = bedrock_claude.invoke_claude(
            system_prompt=system_prompt,
            user_prompt=prompt,
            image_url=image_url,
            max_tokens=RESERVED_OUTPUT_TOKENS,
            temperature=0.7
        )
        
        if not bedrock_response["success"]:
            raise Exception(f"Bedrock API Error: {bedrock_response.get('error', 'Unknown error')}")
        
        print("")
        ai_reply = bedrock_response["content"]
        print(f"Bedrock Response: {ai_reply}")
        token_info = bedrock_response["tokens"]
        print("")
        print(f"Token Info:{token_info}")

        ai_message_data = save_ai_message(user_id, character_id, ai_reply)

        return {
            "success": True,
            "message": ai_reply,
            "timestamp": ai_message_data["timestamp"],
            "tokens": {
                "system_prompt": token_info["system_prompt"],
                "user_prompt": token_info["user_prompt"], 
                "summary_context": safe_token_count(summary_text or ""),
                "recent_chats": safe_token_count(recent_chats_text or ""),
                "output": token_info["output"],
                "total_input": token_info["total_input"],
                "total_output": token_info["total_output"],
                "total_used": token_info["total_used"]
            },
            "usage": bedrock_response.get("usage", {}),
            "userId": str(user_id),
            "characterId": str(character_id)
        }

    except Exception as e:
        traceback.print_exc()
        
        error_message = "⚠️ Sorry, I'm having trouble responding right now."
        detailed_error = f"{error_message}\n\nError: {str(e)}"

        try:
            error_message_data = save_ai_message(user_id, character_id, error_message)
            timestamp = error_message_data["timestamp"]
        except:
            timestamp = datetime.now().isoformat()

        return {
            "success": False,
            "message": detailed_error,
            "timestamp": timestamp,
            "userId": str(user_id),
            "characterId": str(character_id),
            "error":str(e)
        }