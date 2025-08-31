import os
import time
import requests
import base64
from datetime import datetime
from bson import ObjectId
import tiktoken
import google.generativeai as genai
from PIL import Image
import io

from app.config import Config
from app.services.db import db
from app.socket.controller.chat_controller import save_ai_message
from app.utility.claude_reply import claude_token_count, fetch_global_summary, fetch_recent_chats

# Configure Gemini
genai.configure(api_key=Config.GEMINI_API_KEY)

# Initialize Gemini model
model = genai.GenerativeModel('gemini-2.5-flash')

def download_and_process_image(image_url: str) -> dict:
    """Download image from URL and prepare it for Gemini API"""
    try:
        # Download the image
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # Open with PIL to validate and get format
        image = Image.open(io.BytesIO(response.content))
        
        # Convert to RGB if necessary (removes alpha channel)
        if image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save as JPEG to ensure compatibility
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG', quality=85)
        img_data = img_buffer.getvalue()
        
        return {
            "data": img_data,
            "mime_type": "image/jpeg"
        }
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

def upload_image_to_gemini_file_api(image_url: str) -> str:
    """Alternative: Upload image to Gemini File API and return file URI"""
    try:
        # Download the image
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # Save temporarily
        temp_path = f"/tmp/temp_image_{int(time.time())}.jpg"
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        # Upload to Gemini File API
        uploaded_file = genai.upload_file(path=temp_path, mime_type="image/jpeg")
        
        # Clean up temp file
        os.remove(temp_path)
        
        return uploaded_file.uri
    except Exception as e:
        print(f"Error uploading to Gemini File API: {e}")
        return None

def get_claude_reply(prompt: str, user_id: str, character_name: str, character_id: str, image_url: str = None) -> dict:
    start_time = time.perf_counter()
    timings = {}

    def log_step(step_name):
        nonlocal start_time
        elapsed = time.perf_counter() - start_time
        timings[step_name] = round(elapsed, 3)
        print(f"[⏱️] {step_name} completed in {elapsed:.3f} sec")
        start_time = time.perf_counter()

    try:
        # --- Fetch user ---
        try:
            user_object_id = ObjectId(user_id)
            user = db.users.find_one({"_id": user_object_id})
        except:
            user = db.users.find_one({"_id": user_id})
        log_step("Fetch user from DB")

        # --- Load system prompt file ---
        prompt_path = os.path.join("app", "system_prompt", f"{character_name.lower()}.md")
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file '{prompt_path}' not found.")

        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
        log_step("Load system prompt file")

        # --- Replace user details in system prompt ---
        system_prompt = system_prompt.replace("{{userName}}", user.get("userName", "bestie") if user else "bestie")
        system_prompt = system_prompt.replace("{{gender}}", user.get("gender", "") if user else "")
        system_prompt = system_prompt.replace("{{age}}", str(user.get("age", "")) if user else "")
        system_prompt = system_prompt.replace("{{mobileNumber}}", user.get("mobileNumber", "") if user else "")
        log_step("Inject user details into system prompt")

        # --- Fetch memory and recent chats ---
        summary_text = fetch_global_summary(user_id, character_id)
        recent_chats_text = fetch_recent_chats(user_id, character_id)
        log_step("Fetch memory + recent chats")

        # --- Token encoding setup ---
        enc = tiktoken.get_encoding("cl100k_base")
        def safe_token_count(text: str) -> int:
            return len(enc.encode(text))
        log_step("Initialize tokenizer")

        # --- Finalize conversation context ---
        summary_final = summary_text or "No previous conversation history available."
        chats_final = recent_chats_text or "No recent chats available."
        system_prompt = system_prompt.replace("{{conversationSummary}}", summary_final)
        system_prompt = system_prompt.replace("{{recentMessages}}", chats_final)
        log_step("Finalize system prompt with summary + chats")

        # --- Token budgeting ---
        MAX_TOTAL_TOKENS = 2_000_000
        RESERVED_OUTPUT_TOKENS = 8192
        system_tokens = safe_token_count(system_prompt)
        prompt_tokens = safe_token_count(prompt)
        log_step("Token count + budgeting")

        # --- Handle truncation if needed ---
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
        log_step("Truncate context if needed")

        # --- Process image if provided ---
        image_data = None
        if image_url:
            image_data = download_and_process_image(image_url)
            if not image_data:
                # If image processing fails, continue without image
                print(f"Warning: Failed to process image from {image_url}")
        log_step("Process image" if image_url else "Skip image processing")

        # --- Prepare Gemini input ---
        full_prompt = f"{system_prompt}\n\nUser: {prompt}"

        if image_data:
            # Method 1: Using inline data (recommended for most cases)
            response = model.generate_content(
                contents=[
                    {
                        "parts": [
                            {"text": full_prompt},
                            {
                                "inline_data": {
                                    "mime_type": image_data["mime_type"],
                                    "data": base64.b64encode(image_data["data"]).decode('utf-8')
                                }
                            }
                        ]
                    }
                ],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=RESERVED_OUTPUT_TOKENS,
                    temperature=0.7,
                    top_p=1.0,
                )
            )
        else:
            response = model.generate_content(
                contents=[{"parts": [{"text": full_prompt}]}],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=RESERVED_OUTPUT_TOKENS,
                    temperature=0.7,
                    top_p=1.0,
                )
            )
        log_step("Gemini API call")

        # --- Process AI reply ---
        ai_reply = response.text.strip()
        ai_tokens = safe_token_count(ai_reply)
        log_step("Process AI reply")

        # --- Save AI message ---
        ai_message_data = save_ai_message(user_id, character_id, ai_reply)
        log_step("Save AI message to DB")

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
            "characterId": str(character_id),
            "timings": timings
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_message = "⚠️ Sorry, I'm having trouble responding right now."
        detailed_error = f"{error_message}\n\nError: {str(e)}"

        error_message_data = save_ai_message(user_id, character_id, error_message)
        log_step("Error handling")

        return {
            "success": False,
            "message": detailed_error,
            "timestamp": error_message_data["timestamp"],
            "userId": str(user_id),
            "characterId": str(character_id),
            "error": str(e),
            "timings": timings
        }