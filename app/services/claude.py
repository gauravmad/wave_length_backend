import os
from datetime import datetime
from bson import ObjectId
import tiktoken

from app.config import Config
from app.services.db import db
from app.socket.controller.chat_controller import save_ai_message
from app.utility.claude_reply import claude_token_count,fetch_global_summary,fetch_recent_chats
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

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
        MAX_TOTAL_TOKENS = 100_000
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


        if image_url:
            messages =[
                SystemMessage(content=system_prompt),
                HumanMessage(content=[
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{"url":image_url}}
                ])
            ]
        else:
            messages = [
                SystemMessage(content=system_prompt), HumanMessage(content=prompt)
            ]

        # Claude API call
        chat = ChatOpenAI(
            model="anthropic/claude-sonnet-4",
            temperature=0.7,
            max_tokens=RESERVED_OUTPUT_TOKENS,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=Config.ANTHROPIC_API_KEY,
        )

        response = chat.invoke(messages)
        ai_reply = response.content.strip()
        ai_tokens = safe_token_count(ai_reply)

        ai_message_data = save_ai_message(user_id, character_id, ai_reply)

        return {
            "success": True,
            "message": ai_reply,
            "timestamp": ai_message_data["timestamp"],
            "tokens": {
                "system_prompt": system_tokens,
                "user_prompt": prompt_tokens,
                "summary_context": safe_token_count(summary_text or ""),
                "recent_chats": safe_token_count(recent_chats_text or ""),
                "output": ai_tokens,
                "total_used": system_tokens + prompt_tokens + ai_tokens
            },
            "userId": str(user_id),
            "characterId": str(character_id)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_message = "⚠️ Sorry, I'm having trouble responding right now."
        detailed_error = f"{error_message}\n\nError: {str(e)}"

        error_message_data = save_ai_message(user_id, character_id, error_message)

        return {
            "success": False,
            "message": detailed_error,
            "timestamp": error_message_data["timestamp"],
            "userId": str(user_id),
            "characterId": str(character_id),
            "error": str(e)
        }