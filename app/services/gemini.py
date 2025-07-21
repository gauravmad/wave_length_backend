import google.generativeai as genai
from app.config import Config
from app.services.db import db

genai.configure(api_key=Config.GEMINI_API_KEY)

with open("app/system_prompt/zenny.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

def get_gemini_reply(prompt: str, user_id: str) -> str:
    try:
        print(f"Sending prompt to Gemini: {prompt}")
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Fetch chat history for the user from DB
        user_chat = db.chats.find_one({"userId": user_id})
        past_messages = user_chat.get("chatHistory", []) if user_chat else []

        # Format chat history into a single string
        memory = ""
        for chat in past_messages[-10:]:  # last 10 exchanges
            sender = "User" if chat["sender"] == "user" else "AI"
            memory += f"{sender}: {chat['message']}\n"

        # Construct full system prompt with memory + original prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\nHere is the conversation so far:\n{memory}\nUser: {prompt}"

        # Start chat with system-like memory injected as user prompt
        chat = model.start_chat(history=[
            {
                "role": "user",
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ])

        # Send current message (again, as user prompt to get reply)
        response = chat.send_message(prompt)
        print(f"Reply From Gemini",response)
        return response.text.strip()

    except Exception as e:
        print("Gemini Error:", str(e))
        return "⚠️ Failed to connect to Gemini API."