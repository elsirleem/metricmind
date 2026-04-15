# save as test_anthropic.py
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=100,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Return this exact JSON: {\"status\": \"ok\"}"}]
)
print(response.content[0].text)