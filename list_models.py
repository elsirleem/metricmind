# save as test_gemini2.py
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
print("Key loaded:", key[:10] + "..." if key else "NOT FOUND")

genai.configure(api_key=key)

try:
    models = list(genai.list_models())
    print(f"Total models found: {len(models)}")
    for m in models:
        print(f"  {m.name} — methods: {m.supported_generation_methods}")
except Exception as e:
    print(f"Error listing models: {e}")