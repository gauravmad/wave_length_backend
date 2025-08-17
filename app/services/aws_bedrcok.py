import boto3
import json
import base64
import requests
import tiktoken
from typing import Optional, Dict, Any

from app.config import Config

class AWSBedrockClaude:
    def __init__(self):
        self.client = boto3.client(
            service_name="bedrock-runtime",
            region_name=Config.AWS_REGION,
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
        )
        self.model_arn=Config.BEDROCK_MODEL_ARN
        self.encoding=tiktoken.get_encoding("cl100k_base")

    def safe_token_count(self, text:str) -> int:
        try:
            return len(self.encoding.encode(text))
        except Exception:
            return len(text.split()) * 4
            
    def get_image_base64(self,image_url:str) -> tuple[Optional[str],Optional[str]]:
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Convert image to base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')
            
            # Determine media type from content type or URL extension
            content_type = response.headers.get('content-type', '').lower()
            if 'jpeg' in content_type or 'jpg' in image_url.lower():
                media_type = 'image/jpeg'
            elif 'png' in content_type or 'png' in image_url.lower():
                media_type = 'image/png'
            elif 'webp' in content_type or 'webp' in image_url.lower():
                media_type = 'image/webp'
            elif 'gif' in content_type or 'gif' in image_url.lower():
                media_type = 'image/gif'
            else:
                media_type = 'image/jpeg'  # Default fallback
                
            return image_base64, media_type
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None, None
            
    def create_message_content(self, prompt: str, image_url: Optional[str] = None) -> list:
        """Create message content array for Bedrock API"""
        content = []
        
        # Add image if provided
        if image_url:
            image_base64, media_type = self.get_image_base64(image_url)
            if image_base64:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64
                    }
                })
        
        # Add text prompt
        content.append({
            "type": "text",
            "text": prompt
        })
        
        return content        
    
    def invoke_claude(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        image_url: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Invoke Claude via AWS Bedrock"""
        try:
            # Create user message content
            user_content = self.create_message_content(user_prompt, image_url)
            
            # Prepare request body
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_content
                    }
                ]
            }
            
            # Calculate token counts for monitoring
            system_tokens = self.safe_token_count(system_prompt)
            user_tokens = self.safe_token_count(user_prompt)
            
            # Invoke Bedrock
            response = self.client.invoke_model(
                modelId=self.model_arn,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json"
            )
            
            # Parse response
            result = json.loads(response['body'].read())
            
            # Extract Claude's response
            ai_reply = result["content"][0]["text"]
            ai_tokens = self.safe_token_count(ai_reply)
            
            # Get usage statistics if available
            usage_info = result.get("usage", {})
            input_tokens = usage_info.get("input_tokens", system_tokens + user_tokens)
            output_tokens = usage_info.get("output_tokens", ai_tokens)
            
            return {
                "success": True,
                "content": ai_reply,
                "tokens": {
                    "system_prompt": system_tokens,
                    "user_prompt": user_tokens,
                    "output": output_tokens,
                    "total_input": input_tokens,
                    "total_output": output_tokens,
                    "total_used": input_tokens + output_tokens
                },
                "usage": usage_info,
                "raw_response": result
            }
            
        except Exception as e:
            print(f"Error calling AWS Bedrock: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": None
            }


# Global instance
bedrock_claude = AWSBedrockClaude()