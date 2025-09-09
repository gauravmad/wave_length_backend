import os
import time
import requests
import base64
from datetime import datetime, timedelta, timezone
import pytz
from bson import ObjectId
import tiktoken
import anthropic
from PIL import Image
import io
from dotenv import load_dotenv

from app.config import Config
from app.services.db import db
from app.socket.controller.chat_controller import save_ai_message
from app.utility.claude_reply import claude_token_count, fetch_global_summary, fetch_recent_chats

# Load environment variables
load_dotenv()

# Configure Anthropic Claude
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or Config.ANTHROPIC_API_KEY)

def format_timestamp_difference(last_msg_timestamp, current_timestamp):
    """
    Format timestamp difference between last message and current message
    Converts UTC to IST and returns formatted strings
    """
    try:
        # Convert UTC to IST (UTC+5:30)
        ist_tz = pytz.timezone('Asia/Kolkata')
        
        # Handle different timestamp formats
        if isinstance(last_msg_timestamp, datetime):
            if last_msg_timestamp.tzinfo is None:
                # Assume UTC if no timezone info
                last_msg_utc = pytz.utc.localize(last_msg_timestamp)
            else:
                last_msg_utc = last_msg_timestamp.astimezone(pytz.utc)
        else:
            # If it's a string, try to parse it
            last_msg_utc = pytz.utc.localize(datetime.fromisoformat(str(last_msg_timestamp).replace('Z', '')))
        
        if isinstance(current_timestamp, datetime):
            if current_timestamp.tzinfo is None:
                current_utc = pytz.utc.localize(current_timestamp)
            else:
                current_utc = current_timestamp.astimezone(pytz.utc)
        else:
            current_utc = pytz.utc.localize(datetime.fromisoformat(str(current_timestamp).replace('Z', '')))
        
        # Convert to IST
        last_msg_ist = last_msg_utc.astimezone(ist_tz)
        current_ist = current_utc.astimezone(ist_tz)
        
        # Format dates
        def format_datetime(dt):
            day_name = dt.strftime("%A")
            formatted_date = dt.strftime(f"%d %B %Y, %I:%M%p ({day_name})")
            return formatted_date
        
        # Calculate time difference
        time_diff = current_ist - last_msg_ist
        days_diff = time_diff.days
        hours_diff = time_diff.seconds // 3600
        total_hours = days_diff * 24 + hours_diff
        
        # Format last message
        last_msg_formatted = format_datetime(last_msg_ist)
        
        # Add relative time for last message
        if days_diff == 0:
            if total_hours == 0:
                last_msg_relative = "Today"
            else:
                last_msg_relative = "Today"
        elif days_diff == 1:
            last_msg_relative = "Yesterday"
        else:
            last_msg_relative = f"{days_diff} days ago"
        
        last_message_final = f"{last_msg_formatted} - {last_msg_relative}"
        
        # Format current message
        current_msg_formatted = format_datetime(current_ist)
        
        # Add relative time for current message (usually just "Now" or time difference)
        if days_diff == 0 and total_hours < 1:
            current_msg_relative = "Now"
        elif days_diff == 0:
            current_msg_relative = f"{total_hours} hours later"
        elif days_diff == 1:
            current_msg_relative = f"{total_hours} hours later"
        else:
            current_msg_relative = f"{days_diff} days later"
        
        current_message_final = f"{current_msg_formatted} - {current_msg_relative}"
        
        return {
            "last_message": last_message_final,
            "current_message": current_message_final,
            "time_gap_summary": f"Time gap: {days_diff} days, {hours_diff} hours"
        }
        
    except Exception as e:
        print(f"Error formatting timestamps: {e}")
        return {
            "last_message": "Timestamp unavailable",
            "current_message": "Current time",
            "time_gap_summary": "Time gap unknown"
        }

def get_last_user_message_timestamp(user_id: str, character_id: str):
    """
    Get the timestamp of the last user message (not AI message)
    """
    try:
        last_user_msg = db.chats.find_one(
            {
                "userId": str(user_id), 
                "characterId": str(character_id),
                "sender": "user"  # Only get human messages
            },
            sort=[("timestamp", -1)]  # Get the most recent
        )
        
        if last_user_msg and "timestamp" in last_user_msg:
            return last_user_msg["timestamp"]
        return None
    except Exception as e:
        print(f"Error fetching last user message timestamp: {e}")
        return None

def download_and_process_image(image_url: str) -> dict:
    """Download image from URL and prepare it for Claude API"""
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
        
        # Encode to base64 for Claude
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        
        return {
            "data": img_base64,
            "mime_type": "image/jpeg"
        }
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

def get_claude_reply(
    prompt: str, 
    user_id: str, 
    character_name: str, 
    character_id: str, 
    image_url: str = None) -> dict:
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

        # --- Get timestamp information ---
        current_message_timestamp = datetime.utcnow()  # Current UTC time
        last_user_message_timestamp = get_last_user_message_timestamp(user_id, character_id)
        
        timestamp_info = ""
        if last_user_message_timestamp:
            # User has previous messages
            timestamp_data = format_timestamp_difference(last_user_message_timestamp, current_message_timestamp)
            timestamp_info = f"""
Previous message timing: {timestamp_data['last_message']}
Current message timing: {timestamp_data['current_message']}
{timestamp_data['time_gap_summary']}
"""
        else:
            # New user or no previous messages - handle gracefully
            try:
                ist_offset = timedelta(hours=5, minutes=30)
                current_ist = (current_message_timestamp.replace(tzinfo=timezone.utc) + ist_offset)
                formatted_current = current_ist.strftime(f"%d %B %Y, %I:%M%p ({current_ist.strftime('%A')})")
                timestamp_info = f"""
Previous message timing: This is the first message
Current message timing: {formatted_current} - First interaction
Time gap summary: New conversation started
"""
            except Exception as e:
                print(f"Error formatting first message timestamp: {e}")
                timestamp_info = """
Previous message timing: This is the first message
Current message timing: Current time - First interaction
Time gap summary: New conversation started
"""
        
        log_step("Process timestamp information")
        print(f"TimeStamp Info: {timestamp_info}")

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
        
        # --- Add timestamp information to system prompt ---
        system_prompt = system_prompt.replace("{{timestampInfo}}", timestamp_info.strip())

        
        log_step("Inject user details and timestamp info into system prompt")

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

        # --- Token budgeting (Claude Sonnet 4 has 200K context window) ---
        MAX_TOTAL_TOKENS = 200_000
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

        # --- Prepare Claude message content ---
        message_content = []
        
        # Add text content
        message_content.append({
            "type": "text",
            "text": prompt
        })
        
        # Add image content if available
        if image_data:
            message_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_data["mime_type"],
                    "data": image_data["data"]
                }
            })

        # --- Claude API call ---
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=RESERVED_OUTPUT_TOKENS,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": message_content
                }
            ]
        )
        log_step("Claude API call")

        # --- Process AI reply ---
        ai_reply = response.content[0].text.strip()
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
            "timings": timings,
            "model_info": {
                "model": "claude-sonnet-4-20250514",
                "input_tokens": response.usage.input_tokens if hasattr(response, 'usage') else None,
                "output_tokens": response.usage.output_tokens if hasattr(response, 'usage') else None
            },
            "timestamp_info": timestamp_info.strip()  # Include timestamp info in response
        }

    except anthropic.APIError as e:
        import traceback
        traceback.print_exc()
        error_message = "⚠️ Sorry, I'm having trouble responding right now due to API issues."
        detailed_error = f"{error_message}\n\nAPI Error: {str(e)}"

        error_message_data = save_ai_message(user_id, character_id, error_message)
        log_step("API Error handling")

        return {
            "success": False,
            "message": detailed_error,
            "timestamp": error_message_data["timestamp"],
            "userId": str(user_id),
            "characterId": str(character_id),
            "error": f"API Error: {str(e)}",
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