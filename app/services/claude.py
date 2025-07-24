import os
import requests
from app.config import Config
from app.services.db import db
from datetime import datetime

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {Config.ANTHROPIC_API_KEY}",
    "Content-Type": "application/json",
    "X-Title": "WaveAI"
}

def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str) -> str:
    try:
        print(f"Sending prompt to OpenRouter Claude for character '{character_name}'")

        # Load system prompt from file
        prompt_file_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.txt")
        if not os.path.isfile(prompt_file_path):
            raise FileNotFoundError(f"Prompt file '{prompt_file_path}' not found.")

        with open(prompt_file_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        # Fetch last 10 messages (user + ai) between user and this character
        chat_history = list(db.chats.find(
            {"userId": user_id, "characterId": character_id}
        ).sort("timestamp", -1).limit(10))

        # Reverse to maintain chronological order
        chat_history.reverse()

        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        for chat in chat_history:
            role = "user" if chat["sender"] == "user" else "assistant"
            messages.append({"role": role, "content": chat["message"]})

        # Add current prompt
        messages.append({"role": "user", "content": prompt})

        # Prepare payload
        payload = {
            "model": "anthropic/claude-3.5-sonnet",  # Use model supported by OpenRouter
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7
        }

        # Send request to OpenRouter
        response = requests.post(OPENROUTER_API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()

        reply = response.json()["choices"][0]["message"]["content"].strip()
        print("Reply From Claude (OpenRouter):", reply)
        return reply

    except Exception as e:
        print("Claude OpenRouter Error:", str(e))
        return "⚠️ Failed to connect to Claude via OpenRouter."
