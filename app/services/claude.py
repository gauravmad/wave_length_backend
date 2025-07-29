import os
from datetime import datetime
from bson import ObjectId

from app.config import Config
from app.services.db import db

from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str) -> dict:
    try:
        print(f"🔍 Starting get_claude_reply:")
        print(f"   - user_id: {user_id}")
        print(f"   - character_id: {character_id}")
        print(f"   - character_name: {character_name}")
        print(f"   - prompt: {prompt[:50]}...")

        # ✅ 1. Save user message to database FIRST
        user_timestamp = datetime.utcnow().isoformat()
        user_chat_doc = {
            "userId": str(user_id),
            "characterId": str(character_id),
            "sender": "user",
            "message": prompt,
            "timestamp": user_timestamp
        }
        
        print(f"💾 Saving user message to DB...")
        user_result = db.chats.insert_one(user_chat_doc)
        print(f"✅ User message saved with ID: {user_result.inserted_id}")

        # ✅ 2. Fetch user details for personalization
        try:
            user_object_id = ObjectId(user_id)
            user = db.users.find_one({"_id": user_object_id})
        except:
            # Fallback to string ID if ObjectId conversion fails
            user = db.users.find_one({"_id": user_id})
        
        if user:
            print(f"👤 User found: {user.get('userName', 'Unknown')}")
        else:
            print(f"⚠️ No user found for user_id: {user_id}")

        # ✅ 3. Load system prompt file
        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.txt")
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()

        # ✅ 4. Replace placeholders with user details
        if user:
            system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie"))
            system_prompt = system_prompt.replace("{{gender}}", user.get("gender", ""))
            system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", ""))
        else:
            system_prompt = system_prompt.replace("{{userName}}", "bestie")
            system_prompt = system_prompt.replace("{{gender}}", "")
            system_prompt = system_prompt.replace("{{mobileNumber}}", "")

        # Limit prompt size
        system_prompt = system_prompt[:4000]

        # ✅ 5. Fetch chat history (including the message we just saved)
        chat_history = list(db.chats.find({
            "userId": str(user_id),
            "characterId": str(character_id)
        }).sort("timestamp", -1).limit(50))
        
        print(f"💬 Found {len(chat_history)} total messages in history")
        
        # Reverse to get chronological order
        chat_history.reverse()

        # ✅ 6. Build messages for Claude
        messages = [SystemMessage(content=system_prompt)]
        
        for chat in chat_history:
            sender = chat.get("sender", "").strip().lower()
            message_text = chat.get("message", "")
            if not message_text:
                continue
            
            if sender == "user":
                messages.append(HumanMessage(content=message_text))
            elif sender == "ai":
                messages.append(AIMessage(content=message_text))

        print(f"📝 Built {len(messages)} messages for Claude (1 system + {len(messages)-1} history)")

        # ✅ 7. Get Claude response
        chat = ChatOpenAI(
            model="anthropic/claude-3.5-sonnet",
            temperature=0.7,
            max_tokens=1024,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=Config.ANTHROPIC_API_KEY,
        )

        print("🤖 Sending request to Claude...")
        response = chat.invoke(messages)
        ai_reply = response.content.strip()
        print(f"✅ Claude responded with {len(ai_reply)} characters")

        # ✅ 8. Save AI response to database
        ai_timestamp = datetime.utcnow().isoformat()
        ai_chat_doc = {
            "userId": str(user_id),
            "characterId": str(character_id),
            "sender": "ai",
            "message": ai_reply,
            "timestamp": ai_timestamp
        }
        
        print(f"💾 Saving AI response to DB...")
        ai_result = db.chats.insert_one(ai_chat_doc)
        print(f"✅ AI response saved with ID: {ai_result.inserted_id}")

        # ✅ 9. Return structured response for socket
        return {
            "success": True,
            "message": ai_reply,
            "timestamp": ai_timestamp,
            "userId": str(user_id),
            "characterId": str(character_id),
            "user_message_saved": True,
            "ai_message_saved": True
        }

    except Exception as e:
        print(f"❌ Error in get_claude_reply: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # ✅ Save error message to database
        error_message = "⚠️ Sorry, I'm having trouble responding right now."
        error_timestamp = datetime.utcnow().isoformat()
        
        try:
            error_chat_doc = {
                "userId": str(user_id),
                "characterId": str(character_id),
                "sender": "ai",
                "message": error_message,
                "timestamp": error_timestamp
            }
            db.chats.insert_one(error_chat_doc)
            print("💾 Error message saved to DB")
        except Exception as save_error:
            print(f"❌ Failed to save error message: {save_error}")

        return {
            "success": False,
            "message": error_message,
            "timestamp": error_timestamp,
            "userId": str(user_id),
            "characterId": str(character_id),
            "error": str(e)
        }