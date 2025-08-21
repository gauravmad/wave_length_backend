import requests
import tiktoken
from app.config import Config

def get_grok3_response(system_prompt:str, user_prompt:str) -> tuple[str,int]:
    """
        GET Response from Grok-3 for text inputs only
    """

    try:
        url = "https://aastha.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"

        headers = {
            "Content-Type":"application/json",
            "Authorization":f"Bearer {Config.AZURE_SUBSCRIPTION_KEY}"
        }

        data = {
            "messages":[
                {
                    "role":"system",
                    "content":system_prompt
                },
                {
                    "role":"user",
                    "content":user_prompt
                }
            ],
            "max_completion_tokens": 4096,
            "temperature": 0.7,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "model": "grok-3"
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        response_data = response.json()
        ai_reply = response_data["choices"][0]["message"]["content"].strip()
        
        # Calculate tokens for the response
        enc = tiktoken.get_encoding("cl100k_base")
        ai_tokens = len(enc.encode(ai_reply))
        
        return ai_reply, ai_tokens
        
    except Exception as e:
        raise Exception(f"Grok-3 API Error: {str(e)}")    
    

    