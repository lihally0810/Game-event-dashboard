import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

print(f"Testing Key: {api_key[:4]}...{api_key[-4:]}")
try:
    models = genai.list_models()
    print("Successfully listed models:")
    for m in models:
        print(f" - {m.name}")
except Exception as e:
    print(f"Error: {e}")
