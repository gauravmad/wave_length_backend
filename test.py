import boto3
import json
import base64
import requests
from app.config import Config

# Create a Bedrock client in ap-south-1
bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name= Config.AWS_REGION,
    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
)

model_arn = Config.BEDROCK_MODEL_ARN

# Function to download and encode image to base64
def get_image_base64(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        
        # Convert image to base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        
        # Determine media type from content type or URL extension
        content_type = response.headers.get('content-type', '')
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

# Download and encode the image
image_url = "https://socialtix.s3.eu-north-1.amazonaws.com/wave_length_assets/IMG_2433_20250808_040411_d0e2c3f7.jpg"
image_base64, media_type = get_image_base64(image_url)

if image_base64 is None:
    print("Failed to download and encode image")
    exit(1)

# Request body (Anthropic style schema) with base64 encoded image
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 4096,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": "What is in this Image"
                }
            ]
        }
    ]
}

try:
    response = bedrock.invoke_model(
        modelId=model_arn,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )

    result = json.loads(response['body'].read())
    print("")
    print(result["content"][0]["text"])

except Exception as e:
    print(f"Error calling Bedrock: {e}")