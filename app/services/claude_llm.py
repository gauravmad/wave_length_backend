# File: app/services/claude_llm.py

import requests
from typing import List, Optional, ClassVar
from langchain.llms.base import LLM
from app.config import Config

class OpenRouterClaude(LLM):
    model: ClassVar[str] = "anthropic/claude-3.5-sonnet"
    api_url: ClassVar[str] = "https://openrouter.ai/api/v1/chat/completions"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        headers = {
            "Authorization": f"Bearer {Config.ANTHROPIC_API_KEY}",
            "Content-Type": "application/json",
            "X-Title": "WaveAI"
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.7
        }

        response = requests.post(self.api_url, headers=headers, json=payload)
        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]

    @property
    def _llm_type(self) -> str:
        return "custom-openrouter"
