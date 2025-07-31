import os
from datetime import datetime
from bson import ObjectId

from app.config import Config
from app.services.db import db

from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str) -> dict:
    try:
        print(f"\n🔍 Claude Triggered For User: {user_id} | Character: {character_name}")

        # ✅ 1. Fetch user
        try:
            user_object_id = ObjectId(user_id)
            user = db.users.find_one({"_id": user_object_id})
        except:
            user = db.users.find_one({"_id": user_id})

        # ✅ 2. Load system prompt
        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.txt")
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()

        if user:
            system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie"))
            system_prompt = system_prompt.replace("{{gender}}", user.get("gender", ""))
            system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", ""))
        else:
            system_prompt = system_prompt.replace("{{userName}}", "bestie")
            system_prompt = system_prompt.replace("{{gender}}", "")
            system_prompt = system_prompt.replace("{{mobileNumber}}", "")

        # ✅ 3. Token limits
        max_context_tokens = 200000
        system_tokens = estimate_tokens(system_prompt)
        prompt_tokens = estimate_tokens(prompt)
        reserved_output_tokens = 4096
        remaining_tokens = max_context_tokens - (system_tokens + prompt_tokens + reserved_output_tokens)

        print(f"🧠 Token Budget → History: {remaining_tokens} tokens")

        # ✅ 4. Fetch chat history
        chat_history = list(db.chats.find({
            "userId": str(user_id),
            "characterId": str(character_id)
        }).sort("timestamp", -1))

        messages = [SystemMessage(content=system_prompt)]
        total_history_tokens = 0
        added_messages = 0

        for chat in reversed(chat_history):
            sender = chat.get("sender", "").lower()
            text = chat.get("message", "")
            token_count = estimate_tokens(text)

            if total_history_tokens + token_count > remaining_tokens:
                break

            if sender == "user":
                messages.append(HumanMessage(content=text))
            elif sender == "ai":
                messages.append(AIMessage(content=text))

            total_history_tokens += token_count
            added_messages += 1

        messages.append(HumanMessage(content=prompt))

        print(f"📚 Chat Context → {added_messages} messages, {total_history_tokens} tokens")

        # ✅ 5. Call Claude
        chat = ChatOpenAI(
            model="anthropic/claude-3.5-sonnet",
            temperature=0.7,
            max_tokens=4096,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=Config.ANTHROPIC_API_KEY,
        )

        print("🤖 Sending to Claude...")
        response = chat.invoke(messages)
        ai_reply = response.content.strip()
        ai_tokens = estimate_tokens(ai_reply)

        print(f"✅ Claude Response: {len(ai_reply)} chars (~{ai_tokens} tokens)")

        # ✅ 6. Save AI response
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
                "chat_history": total_history_tokens,
                "output": ai_tokens,
                "total_used": system_tokens + prompt_tokens + total_history_tokens + ai_tokens
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
