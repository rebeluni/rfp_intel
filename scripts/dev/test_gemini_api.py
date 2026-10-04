import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
resp = httpx.post(
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent",
    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    json={
        "contents": [{"parts": [{"text": "Reply in JSON: {\"status\": \"ok\"}"}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0}
    },
    timeout=30.0
)
print("Status:", resp.status_code)
print("Body:", resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text"))
print("usageMetadata:", resp.json().get("usageMetadata"))
