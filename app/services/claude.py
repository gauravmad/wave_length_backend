import os
from datetime import datetime
from bson import ObjectId
import tiktoken

from app.config import Config
from app.services.db import db
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI


# ------------------------- Token Counter ------------------------- #
def claude_token_count(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ------------------------- Global Summary Fetcher ------------------------- #
def fetch_global_summary(user_id: str, character_id: str) -> str:
    """
    Fetch the global summary for the user-character pair.
    Returns the summary text or empty string if not found.
    """
    summary_doc = db.summaries.find_one({
        "userId": user_id,
        "characterId": character_id
    })
    
    if summary_doc and summary_doc.get("summary"):
        return summary_doc["summary"]
    
    return ""


# ------------------------- Claude Invocation ------------------------- #
def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str) -> dict:
    try:
        print(f"\n🔍 Claude Triggered For User: {user_id} | Character: {character_name}")

        # ✅ Fetch user
        try:
            user_object_id = ObjectId(user_id)
            user = db.users.find_one({"_id": user_object_id})
        except:
            user = db.users.find_one({"_id": user_id})

        # ✅ Load system prompt
        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.txt")
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()

        # ✅ Replace user placeholders
        if user:
            system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie"))
            system_prompt = system_prompt.replace("{{gender}}", user.get("gender", ""))
            system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", ""))
        else:
            system_prompt = system_prompt.replace("{{userName}}", "bestie")
            system_prompt = system_prompt.replace("{{gender}}", "")
            system_prompt = system_prompt.replace("{{mobileNumber}}", "")

        # ✅ Fetch global summary
        summary_text = fetch_global_summary(user_id, character_id)
        
        # ✅ Integrate summary into system prompt
        if summary_text:
            # Replace the {{conversationMemory}} placeholder with actual summary
            final_system_prompt = system_prompt.replace("{{conversationMemory}}", summary_text)
            print(f"✅ Memory integrated: {claude_token_count(summary_text)} tokens")
        else:
            # Remove the memory placeholder if no summary exists
            final_system_prompt = system_prompt.replace("{{conversationMemory}}", "No previous conversation history available.")
            print("⚠️ No conversation memory available")

        # ✅ Token budgeting
        MAX_TOTAL_TOKENS = 100_000
        RESERVED_OUTPUT_TOKENS = 4096
        system_tokens = claude_token_count(final_system_prompt)
        prompt_tokens = claude_token_count(prompt)

        remaining_budget = MAX_TOTAL_TOKENS - system_tokens - prompt_tokens - RESERVED_OUTPUT_TOKENS

        # Check if we're over budget
        if remaining_budget < 0:
            print(f"⚠️ Over token budget by {abs(remaining_budget)} tokens. Truncating summary...")
            # If over budget, truncate the summary
            if summary_text:
                # Calculate how much we need to reduce
                excess = abs(remaining_budget)
                target_summary_tokens = claude_token_count(summary_text) - excess - 100  # 100 token buffer
                
                if target_summary_tokens > 0:
                    # Truncate summary
                    enc = tiktoken.get_encoding("cl100k_base")
                    tokens = enc.encode(summary_text)
                    truncated_tokens = tokens[:target_summary_tokens]
                    truncated_summary = enc.decode(truncated_tokens)
                    
                    final_system_prompt = system_prompt.replace("{{conversationMemory}}", 
                        f"[Conversation history truncated]\n\n{truncated_summary}")
                else:
                    # Remove summary entirely if too large
                    final_system_prompt = system_prompt.replace("{{conversationMemory}}", 
                        "Previous conversation history too large to include.")
                
                system_tokens = claude_token_count(final_system_prompt)

        # ✅ Compose messages
        messages = [SystemMessage(content=final_system_prompt)]
        messages.append(HumanMessage(content=prompt))

        print(f"📊 Token Usage:")
        print(f"   System (with memory): {system_tokens}")
        print(f"   User Prompt: {prompt_tokens}")
        print(f"   Reserved Output: {RESERVED_OUTPUT_TOKENS}")
        print(f"   Total Messages: {len(messages)}")

        # ✅ Claude call
        chat = ChatOpenAI(
            model="anthropic/claude-sonnet-4",
            temperature=0.7,
            max_tokens=RESERVED_OUTPUT_TOKENS,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=Config.ANTHROPIC_API_KEY,
        )

        print("🤖 Sending to Claude...")
        response = chat.invoke(messages)
        ai_reply = response.content.strip()
        ai_tokens = claude_token_count(ai_reply)

        print(f"✅ Claude Response: {len(ai_reply)} chars (~{ai_tokens} tokens)")

        # ✅ Save response to DB
        ai_timestamp = datetime.utcnow().isoformat()
        db.chats.insert_one({
            "userId": str(user_id),
            "characterId": str(character_id),
            "sender": "ai",
            "message": ai_reply,
            "timestamp": ai_timestamp
        })

        return {
            "success": True,
            "message": ai_reply,
            "timestamp": ai_timestamp,
            "tokens": {
                "system_prompt": system_tokens,
                "user_prompt": prompt_tokens,
                "summary_context": claude_token_count(summary_text) if summary_text else 0,
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
        error_timestamp = datetime.utcnow().isoformat()

        try:
            db.chats.insert_one({
                "userId": str(user_id),
                "characterId": str(character_id),
                "sender": "ai",
                "message": error_message,
                "timestamp": error_timestamp
            })
        except:
            pass

        return {
            "success": False,
            "message": error_message,
            "timestamp": error_timestamp,
            "userId": str(user_id),
            "characterId": str(character_id),
            "error": str(e)
        }