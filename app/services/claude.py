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


# ------------------------- Summary Fetcher ------------------------- #
def fetch_all_summaries(user_id: str, character_id: str) -> list[str]:
    doc = db.summaries.find_one({
        "userId": user_id,
        "characterId": character_id
    })

    if not doc or not doc.get("summaries"):
        return []

    # sort by createdAt ascending (oldest to newest)
    return [s["summary"] for s in sorted(doc["summaries"], key=lambda x: x["createdAt"])]


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

        if user:
            system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie"))
            system_prompt = system_prompt.replace("{{gender}}", user.get("gender", ""))
            system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", ""))
        else:
            system_prompt = system_prompt.replace("{{userName}}", "bestie")
            system_prompt = system_prompt.replace("{{gender}}", "")
            system_prompt = system_prompt.replace("{{mobileNumber}}", "")

        # ✅ Token budgeting
        MAX_TOTAL_TOKENS = 100_000
        RESERVED_OUTPUT_TOKENS = 4096
        system_tokens = claude_token_count(system_prompt)
        prompt_tokens = claude_token_count(prompt)

        remaining_budget = MAX_TOTAL_TOKENS - system_tokens - prompt_tokens - RESERVED_OUTPUT_TOKENS

        # ✅ Fetch all summaries
        summary_blocks = fetch_all_summaries(user_id, character_id)
        print("Summary Blocks", summary_blocks)
        summary_text = "\n\n".join(summary_blocks)
        print("Summary Text", summary_text)
        summary_token_count = claude_token_count(summary_text)

        # Truncate if too large
        if summary_token_count > remaining_budget:
            # Keep only what fits
            truncated = ""
            total = 0
            for summary in summary_blocks:
                t = claude_token_count(summary)
                if total + t > remaining_budget:
                    break
                truncated += summary + "\n\n"
                total += t
            summary_text = truncated.strip()
            summary_token_count = total

        # ✅ Compose messages
        messages = [SystemMessage(content=system_prompt)]

        if summary_text:
            messages.append(HumanMessage(content=f"Here is a summary of our past conversations:\n\n{summary_text}"))

        messages.append(HumanMessage(content=prompt))

        print(f"📚 Summary Context → {len(summary_blocks)} blocks, {summary_token_count} tokens")

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
                "summary_context": summary_token_count,
                "output": ai_tokens,
                "total_used": system_tokens + prompt_tokens + summary_token_count + ai_tokens
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
