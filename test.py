import boto3
import json

# Create a Bedrock client in us-east-1
bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1",
    aws_access_key_id="AKIAYZCR7773J7DDPKAC",
    aws_secret_access_key="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"
)

model_arn = "arn:aws:bedrock:ap-south-1:603614871542:inference-profile/apac.anthropic.claude-sonnet-4-20250514-v1:0"

# Request body (Anthropic style schema)
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 256,
    "messages": [
        {"role": "user", "content": "Hello, how are you?"}
    ]
}

response = bedrock.invoke_model(
    modelId=model_arn,  # ✅ use inference profile ARN here
    body=json.dumps(body),
    contentType="application/json",
    accept="application/json"
)


result = json.loads(response['body'].read())
print(f"Result: {result}")
print("")
print(result["content"][0]["text"])
