import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # read .env into environment variables

client = OpenAI()  # finds OPENAI_API_KEY automatically
model = os.environ["MODEL_SMALL"]  # from .env, never hard-coded

response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Reply with exactly: key works"}],
)

print(f"Model: {model}")
print(f"Reply: {response.choices[0].message.content}")
