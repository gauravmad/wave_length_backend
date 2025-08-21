import os
from openai import AzureOpenAI
from app.config import Config

endpoint = "https://aastha.cognitiveservices.azure.com/"
model_name = "gpt-4.1"
deployment = "gpt-4.1"

subscription_key = Config.AZURE_SUBSCRIPTION_KEY
api_version = "2024-12-01-preview"

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

response = client.chat.completions.create(
    messages=[
        {
            "role":"user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe this image:"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://socialtix.s3.eu-north-1.amazonaws.com/wave_length_assets/d3f2e550-acb6-4201-8552-687e3c53554b.jpg"
                    }
                }
            ]
        }
    ],
    max_completion_tokens=13107,
    temperature=1.0,
    top_p=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    model=deployment
)

print(response.choices[0].message.content)