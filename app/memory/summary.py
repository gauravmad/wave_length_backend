import os
from datetime import datetime
import google.generativeai as genai
from app.config import Config
from app.services.db import db
from pymongo import ReturnDocument

# Configure Gemini
genai.configure(api_key=Config.GEMINI_API_KEY)

def load_summary_prompt(user_name: str = "User") -> str:
    # print("User Name",user_name)
    prompt_path = os.path.join("app", "system_prompt", "summarize.md")
    if not os.path.isfile(prompt_path):
        raise FileNotFoundError("🛑 summary.md is missing inside system_prompt folder.")

    with open(prompt_path, "r", encoding="utf-8") as file:
        template = file.read()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    prompt = template.replace("{{userName}}", user_name)
    prompt = prompt.replace("{{today's date}}", today)

    return prompt.strip()

def summarize_incremental(previous_summary: str, new_message: str, user_name: str) -> str:
    # Load system prompt from inputsummary.txt
    prompt_path = os.path.join("app", "system_prompt", "inputsummary.md")

    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    # Replace placeholder if present
    system_prompt = system_prompt.replace("{{userName}}", user_name or "User")

    # Human instructions and input
    human_message = (
        f"Current Summary:\n\n{previous_summary.strip()}\n\n"
        f"New Chat Message:\n{new_message.strip()}"
    )

    # Combine system and human message for Gemini
    full_prompt = f"{system_prompt}\n\n{human_message}"

    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Configure generation parameters
    generation_config = genai.types.GenerationConfig(
        max_output_tokens=2048,
        temperature=0.4,
    )

    response = model.generate_content(
        full_prompt,
        generation_config=generation_config
    )
    
    print(f"🧠 Gemini Summary Response: {response.text}")
    return response.text.strip()


def summarize_from_scratch(chats: list, user_name: str) -> str:
    context = ""
    for chat in chats:
        sender_raw = chat.get("sender", "").lower()
        sender = "You" if sender_raw == "user" else "Zenny" if sender_raw == "ai" else sender_raw.capitalize()
        message = chat.get("message", "").strip()
        if message:
            context += f"{sender}: {message}\n"

    if not context.strip():
        return ""

    system_prompt = load_summary_prompt(user_name)
    human_message = f"Based on this chat, generate the structured summary:\n\n{context.strip()}"
    
    # Combine system and human message for Gemini
    full_prompt = f"{system_prompt}\n\n{human_message}"

    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Configure generation parameters
    generation_config = genai.types.GenerationConfig(
        max_output_tokens=2048,
        temperature=0.4,
    )

    response = model.generate_content(
        full_prompt,
        generation_config=generation_config
    )
    
    return response.text.strip()


# Creates a new Global Summary
def create_global_summary(user_id: str, character_id: str):

    now = datetime.utcnow()

    user = db.users.find_one({"_id": user_id}) or {}
    user_name = user.get("userName", "User")

    chats = list(db.chats.find({
        "userId": user_id,
        "characterId": character_id
    }).sort("timestamp", 1))
    print(f"{len(chats)} chats fetched")

    summary_text = summarize_from_scratch(chats, user_name)
    if not summary_text:
        return
    
    existing_summary = db.summaries.find_one({
        "userId":user_id,
        "characterId":character_id
    })

    if existing_summary:
        db.summaries.find_one_and_update(
            {"_id":existing_summary["_id"]},
            {
                "$set":{
                    "summary":summary_text,
                    "updatedAt":now
                }
            },
            return_document=ReturnDocument.AFTER
        )
        print("🔁 Updated existing global summary.")
    else:
        # Insert a new summary
        db.summaries.insert_one({
            "userId": user_id,
            "characterId": character_id,
            "summary": summary_text,
            "updatedAt": now
        })
        print("✅ Created new global summary.")
    return summary_text

# Extract Summary for the New Message
def update_summary_with_new_message(user_id: str, character_id: str, new_message: str):

    print(f"Generating Summary for{new_message}")

    now = datetime.utcnow()

    summary_doc = db.summaries.find_one({
        "userId": user_id,
        "characterId": character_id
    })

    user = db.users.find_one({"_id": user_id}) or {}
    user_name = user.get("userName", "User")
    print("User Name",user_name)

    if not summary_doc:
        print("📄 No summary exists. Creating a new one.")
        create_global_summary(user_id, character_id)
        return

    updated_summary = summarize_incremental(
        previous_summary=summary_doc["summary"],
        new_message=new_message,
        user_name=user_name
    )

    db.summaries.update_one(
        {"_id": summary_doc["_id"]},
        {
            "$set": {
                "summary": updated_summary,
                "updatedAt": now
            }
        }
    )
    # print("✅ Global summary updated.", updated_summary)
    return updated_summary

# Compress Summary
def compress_summary(summary: str) -> str:
    prompt_path = os.path.join("app", "system_prompt", "compressSummary.md")

    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    full_prompt = f"{system_prompt}\n\n{summary}"

    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Configure generation parameters
    generation_config = genai.types.GenerationConfig(
        max_output_tokens=1024,
        temperature=0.3,
    )

    response = model.generate_content(
        full_prompt,
        generation_config=generation_config
    )
    
    print(f"🧠 Compressed Summary: {response.text}")
    return response.text.strip()