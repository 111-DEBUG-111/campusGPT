import asyncio
from google import genai
from app.config import get_settings

settings = get_settings()
client = genai.Client(api_key=settings.gemini_api_key)

def list_models():
    for model in client.models.list():
        print(f"Name: {model.name}, Supported Methods: {model.supported_actions}")

list_models()
