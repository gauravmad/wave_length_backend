# app/services/ai/gemini_service.py
import base64
import google.generativeai as genai
from typing import Optional, Dict

from app.config import Config


class GeminiService:
    """Service class for handling Gemini AI operations"""
    
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    def generate_response(
        self, 
        full_prompt: str, 
        image_data: Optional[Dict] = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.7
    ) -> str:
        """Generate response from Gemini AI"""
        try:
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                top_p=1.0,
            )
            
            if image_data:
                # Generate response with image
                response = self.model.generate_content(
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
                    generation_config=generation_config
                )
            else:
                # Generate text-only response
                response = self.model.generate_content(
                    contents=[{"parts": [{"text": full_prompt}]}],
                    generation_config=generation_config
                )
            
            return response.text.strip()
            
        except Exception as e:
            print(f"❌ Error generating Gemini response: {e}")
            raise e